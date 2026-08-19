"""The three flow stages, each with a verification gate.

Secrets (username/password/OTP) are injected here by deterministic code straight into the
page — they never pass through the LLM.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from playwright.async_api import Frame, Page

from . import detect

_OTP_SUBMIT = re.compile(r"verify|submit|continue|confirm|next|sign ?in", re.I)


async def _wait_for(check, tries: int = 20, delay: float = 0.5) -> bool:
    for _ in range(tries):
        if await check():
            return True
        await asyncio.sleep(delay)
    return False


# --- Stage 1: login --------------------------------------------------------------------

async def _submit_login(frame: Frame, username: str, password: str, *, with_password: bool) -> None:
    if await frame.locator('[data-al="username"]').count():
        await frame.fill('[data-al="username"]', username, timeout=10000)
    if with_password:
        await frame.fill('[data-al="password"]', password, timeout=10000)
    btn = frame.locator('[data-al="submit"]')
    if await btn.count():
        await btn.first.click(timeout=10000)
    elif with_password:
        await frame.locator('[data-al="password"]').press("Enter")
    else:
        await frame.locator('[data-al="username"]').press("Enter")


async def stage_login(page: Page, base_url: str, username: str, password: str) -> tuple[bool, str, dict]:
    recipe = {"needs_trigger": False, "two_step": False}
    await page.goto(base_url, wait_until="domcontentloaded")
    await detect._settle(page)

    frame, info = await detect.scan_for_login(page, require_password=True)
    if frame is None and await detect.click_login_trigger(page):
        recipe["needs_trigger"] = True
        frame, info = await detect.scan_for_login(page, require_password=True)

    if frame is None:                                   # maybe a two-step (username first)
        frame, info = await detect.scan_for_login(page, require_password=False)
        if frame is not None:
            recipe["two_step"] = True
            await _submit_login(frame, username, password, with_password=False)
            await detect._settle(page)
            frame, info = await detect.scan_for_login(page, require_password=True)

    if frame is None:
        return False, "login form not found", recipe

    await _submit_login(frame, username, password, with_password=True)
    await detect._settle(page)

    # Gate: the OTP step must now be present.
    reached = await _wait_for(lambda: _otp_reached(page))
    if not reached:
        return False, "login submitted but OTP page did not appear (credentials rejected?)", recipe
    return True, "login accepted, OTP page reached", recipe


async def _otp_reached(page: Page) -> bool:
    if "otp" in page.url.lower():
        return True
    return await detect.find_otp_field(page) is not None


# --- Stage 2: OTP ----------------------------------------------------------------------

async def stage_otp(page: Page, reader, bank_name: str, user_id: str, since_ts: float,
                    redactor) -> tuple[bool, str, str | None]:
    frame = await detect.find_otp_field(page)
    if frame is None:
        return False, "OTP field not found", None

    code = reader.fetch_otp(bank_name=bank_name, user_id=user_id, since_ts=since_ts)
    if not code:
        return False, "OTP email not received", None
    redactor.add(code)                                  # never let the code hit a log

    await frame.fill('[data-al="otp"]', code, timeout=10000)
    btn = frame.get_by_role("button", name=_OTP_SUBMIT)
    if await btn.count():
        await btn.first.click(timeout=10000)
    else:
        await frame.locator('[data-al="otp"]').press("Enter")
    await detect._settle(page)

    reached = await _wait_for(lambda: _statements_reached(page))
    if not reached:
        return False, "OTP submitted but statements page did not appear (wrong/expired code?)", code
    return True, "OTP accepted, statements page reached", code


async def _statements_reached(page: Page) -> bool:
    if "statements" in page.url.lower():
        return True
    _frame, rows = await detect.collect_statements(page)
    return len(rows) > 0


# --- Stage 3: statement download -------------------------------------------------------

async def stage_statement(page: Page, dl_dir: Path, bank_id: str, llm) -> tuple[bool, str, str | None]:
    frame, options = await detect.collect_statements(page)
    if not options:
        return False, "no statements listed", None

    latest_id = llm.select_latest_statement(options)
    target = next((o for o in options if o["id"] == latest_id), options[0])

    dl_dir.mkdir(parents=True, exist_ok=True)
    dest = dl_dir / f"{bank_id}_{target['id']}.pdf"
    try:
        # Download can be initiated from within a child frame; expect_download is page-level.
        async with page.expect_download(timeout=15000) as dl_info:
            await frame.locator(f'a[data-download="statement"][href$="{target["id"]}.pdf"]').first.click()
        download = await dl_info.value
        await download.save_as(str(dest))
    except Exception as exc:
        return False, f"download failed: {type(exc).__name__}", None

    if not _is_pdf(dest):
        return False, "downloaded file is not a valid PDF", None
    return True, f"downloaded latest statement ({target['id']})", str(dest)


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-" and path.stat().st_size > 0
    except Exception:
        return False
