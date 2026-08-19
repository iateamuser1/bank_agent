"""Page detection: login form, OTP field, statement links.

The login detector is the same frame/shadow-aware, selector-free approach proven in the
auto-login phase: mark the fields in the browser, act on the marks with Playwright. Here it
also drives the mock banks' modal / two-step / iframe layouts.
"""

from __future__ import annotations

import asyncio
import re

from playwright.async_api import Frame, Page

TRIGGER_WORDS = re.compile(r"sign ?in|log ?in|login|account", re.I)

# Marks the login fields with data-al attributes; mirrors auto-login's JS_MARK_LOGIN.
JS_MARK_LOGIN = r"""
() => {
  const vis = (el) => { if (!el) return false; const s = getComputedStyle(el);
    if (s.display==='none'||s.visibility==='hidden'||Number(s.opacity)===0) return false;
    const r = el.getBoundingClientRect(); return r.width>0 && r.height>0; };
  const textLike = (i) => ['text','email','tel',''].includes((i.getAttribute('type')||'text').toLowerCase());
  document.querySelectorAll('[data-al]').forEach(e => e.removeAttribute('data-al'));
  const pwd = [...document.querySelectorAll('input[type="password"]')].find(vis) || null;
  let user = null;
  if (pwd) {
    pwd.setAttribute('data-al','password');
    const scope = pwd.form || document;
    const inputs = [...scope.querySelectorAll('input')].filter(i => textLike(i) && vis(i));
    for (const i of inputs) if (i.compareDocumentPosition(pwd) & Node.DOCUMENT_POSITION_FOLLOWING) user = i;
    if (!user && inputs.length) user = inputs[0];
  } else {
    const inputs = [...document.querySelectorAll('input')].filter(i => textLike(i) && vis(i));
    const score = (i) => { const s=[i.name,i.id,i.autocomplete,i.getAttribute('aria-label'),i.placeholder].join(' ').toLowerCase();
      let n=0; if (i.type==='email'||/email/.test(s)) n+=2; if (/user|login/.test(s)) n+=2; return n; };
    inputs.sort((a,b)=>score(b)-score(a));
    user = inputs.find(i => score(i) > 0) || null;
  }
  if (user) user.setAttribute('data-al','username');
  const fs = (pwd && pwd.form) || (user && user.form) || document;
  let submit = fs.querySelector('button[type="submit"], input[type="submit"]');
  if (!submit) { const re=/sign ?in|log ?in|continue|submit|next/i;
    submit = [...document.querySelectorAll('button,input[type=submit],[role=button]')].filter(vis)
      .find(b => re.test((b.innerText||b.value||'').trim())) || null; }
  if (submit) submit.setAttribute('data-al','submit');
  return { hasPassword: !!pwd, hasUsername: !!user, hasSubmit: !!submit };
}
"""

# Marks the OTP input with data-al="otp".
JS_MARK_OTP = r"""
() => {
  const vis = (el) => { const s=getComputedStyle(el); const r=el.getBoundingClientRect();
    return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0; };
  document.querySelectorAll('[data-al="otp"]').forEach(e=>e.removeAttribute('data-al'));
  const cand = [...document.querySelectorAll('input')].filter(vis).find(i => {
    const s=[i.name,i.id,i.autocomplete,i.placeholder,i.getAttribute('inputmode')].join(' ').toLowerCase();
    return i.autocomplete==='one-time-code' || /otp|one.?time|code|verif/.test(s); });
  if (cand) { cand.setAttribute('data-al','otp'); return true; }
  return false;
}
"""

JS_COLLECT_STATEMENTS = r"""
() => [...document.querySelectorAll('a[data-download="statement"]')].map(a => {
  const row = a.closest('tr');
  const dcell = row ? row.querySelector('[data-stmt-date]') : null;
  const m = a.getAttribute('href').match(/statement\/([^.]+)\.pdf/);
  return { id: m ? m[1] : a.getAttribute('href'), href: a.href,
           date: dcell ? dcell.getAttribute('data-stmt-date') : '' };
})
"""


async def _settle(page: Page) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass


async def scan_for_login(page: Page, *, require_password: bool):
    for frame in page.frames:
        try:
            info = await asyncio.wait_for(frame.evaluate(JS_MARK_LOGIN), timeout=5)
        except Exception:
            continue
        if info["hasPassword"] or (not require_password and info["hasUsername"] and info["hasSubmit"]):
            return frame, info
    return None, None


async def click_login_trigger(page: Page) -> bool:
    for cand in (page.get_by_role("button", name=TRIGGER_WORDS),
                 page.get_by_role("link", name=TRIGGER_WORDS)):
        if await cand.count():
            try:
                await cand.first.click(timeout=4000)
                await _settle(page)
                return True
            except Exception:
                continue
    return False


async def find_otp_field(page: Page) -> Frame | None:
    for frame in page.frames:
        try:
            if await asyncio.wait_for(frame.evaluate(JS_MARK_OTP), timeout=5):
                return frame
        except Exception:
            continue
    return None


async def collect_statements(page: Page) -> tuple[Frame | None, list[dict]]:
    """Return (frame, rows) — the frame matters because in the iframe bank the whole flow,
    including the statements table, lives inside a child frame."""
    for frame in page.frames:
        try:
            rows = await frame.evaluate(JS_COLLECT_STATEMENTS)
        except Exception:
            continue
        if rows:
            return frame, rows
    return None, []
