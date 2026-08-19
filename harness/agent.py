"""Orchestrator: run the three gated stages for one (bank, user), with memory and retries.

Perceive -> act -> verify, one stage at a time; a stage that fails its gate is retried a
bounded number of times before the job stops at that stage. Everything worth remembering
goes to the journal (resumable) and the per-bank recipe (replayable).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from pathlib import Path

from playwright.async_api import async_playwright

from ..banks.registry import BANKS, bank_url
from .email_reader import OtpReader
from .llm import LLM
from .memory import Journal, RecipeCache
from .stages import stage_login, stage_otp, stage_statement
from .vault import Redactor, Vault

_ROOT = Path(__file__).resolve().parents[1]
_STAGE_RETRIES = 2


@dataclass
class JobResult:
    bank_id: str
    user_id: str
    stage_reached: str          # login | otp | statement
    status: str                 # SUCCESS | FAILED
    reason: str
    statement_path: str | None
    duration_ms: int


async def _with_retry(coro_factory, tries: int = _STAGE_RETRIES):
    last = (False, "not attempted", None)
    for _ in range(tries):
        result = await coro_factory()
        if result[0]:
            return result
        last = result
    return last


async def run_job(bank_id: str, user_id: str, cfg: dict, headless: bool = True,
                  on_progress=None) -> JobResult:
    """Run the three gated stages for one (bank, user).

    `on_progress(stage, state, detail)` is an optional observer called as each stage starts
    and settles — state is "running" | "done" | "failed". It is advisory: the UI uses it to
    draw a progress bar, and a misbehaving observer must never fail the job.
    """
    bank = BANKS[bank_id]
    vault = Vault()
    user = vault.user(user_id)
    redactor = Redactor(vault.all_static_secrets())
    llm = LLM(cfg, vault.azure())
    reader = OtpReader(cfg, vault, llm)
    journal = Journal(redactor)
    recipe_cache = RecipeCache(bank_id)

    base = bank_url(f"http://{cfg['banks']['host']}:{cfg['banks']['port']}", bank_id)
    dl_dir = _ROOT / cfg["downloads_dir"] / bank_id / user_id
    start = time.monotonic()

    def result(stage, status, reason, path=None):
        r = JobResult(bank_id, user_id, stage, status, reason, path,
                      int((time.monotonic() - start) * 1000))
        journal.write(event="job_done", **asdict(r))
        return r

    def progress(stage: str, state: str, detail: str = "") -> None:
        if on_progress is None:
            return
        try:
            on_progress(stage, state, detail)
        except Exception:                       # an observer must not break the run
            pass

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        page.set_default_timeout(20000)
        try:
            since_ts = time.time()

            progress("login", "running")
            ok, reason, recipe = await _with_retry(
                lambda: stage_login(page, base, user.portal_username, user.portal_password))
            journal.write(event="stage", bank=bank_id, user=user_id, stage="login", ok=ok, reason=reason)
            progress("login", "done" if ok else "failed", reason)
            if not ok:
                return result("login", "FAILED", reason)
            recipe_cache.save(recipe)                   # remember this bank's login shape

            progress("otp", "running")
            ok, reason, _code = await _with_retry(
                lambda: stage_otp(page, reader, bank.name, user_id, since_ts, redactor))
            journal.write(event="stage", bank=bank_id, user=user_id, stage="otp", ok=ok, reason=reason)
            progress("otp", "done" if ok else "failed", reason)
            if not ok:
                return result("otp", "FAILED", reason)

            progress("statement", "running")
            ok, reason, path = await _with_retry(
                lambda: stage_statement(page, dl_dir, bank_id, llm))
            journal.write(event="stage", bank=bank_id, user=user_id, stage="statement", ok=ok, reason=reason)
            progress("statement", "done" if ok else "failed", reason)
            if not ok:
                return result("statement", "FAILED", reason)

            return result("statement", "SUCCESS", reason, path)
        finally:
            await context.close()
            await browser.close()
