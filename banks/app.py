"""The mock bank web app: one FastAPI application serving all 20 portals under /bank/<id>/.

Flow per bank:  home (login, layout varies) -> POST login (verify) -> OTP page (code emailed)
-> POST otp (verify) -> statements -> download PDF.
"""

from __future__ import annotations

import time
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.middleware.sessions import SessionMiddleware

from . import data, mailer
from .pdfgen import statement_pdf
from .registry import BANKS
from .templates import render

_ROOT = Path(__file__).resolve().parents[1]


def _load_config() -> dict:
    return yaml.safe_load((_ROOT / "config.yaml").read_text(encoding="utf-8"))


def _load_secrets() -> dict:
    vault = _ROOT / "secrets" / "vault.yaml"
    return yaml.safe_load(vault.read_text(encoding="utf-8")) if vault.exists() else {}


def create_app() -> FastAPI:
    cfg = _load_config()
    secrets = _load_secrets()
    # Resolve the maildir against the project root so the OTP reader finds it regardless of cwd.
    cfg["mail"]["maildir"] = str(_ROOT / cfg["mail"]["maildir"])
    app = FastAPI(title="Mock Bank Portals")
    app.add_middleware(SessionMiddleware, secret_key="mock-bank-dev-key")

    def state(request: Request, bid: str) -> dict:
        return request.session.setdefault(bid, {})

    def base(bid: str) -> str:
        return f"/bank/{bid}/"

    def require_bank(bid: str):
        bank = BANKS.get(bid)
        if bank is None:
            return None
        return bank

    # --- home / login page (layout depends on the bank's variant) --------------------
    @app.get("/bank/{bid}/", response_class=HTMLResponse)
    def home(bid: str, request: Request):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        return HTMLResponse(render(bank.variant, bank=bank, base=base(bid), error=None))

    @app.get("/bank/{bid}/login-frame", response_class=HTMLResponse)
    def login_frame(bid: str, request: Request):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        return HTMLResponse(render("iframe_frame", bank=bank, base=base(bid), error=None))

    # --- credential submission -------------------------------------------------------
    @app.post("/bank/{bid}/login")
    def login(bid: str, request: Request, username: str = Form(""), password: str = Form(None)):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)

        # Two-step variant: first POST carries only the username.
        if password is None:
            if data.find_user_by_username(username):
                st["pending_user"] = username
                request.session[bid] = st
                return RedirectResponse(base(bid) + "login-password", status_code=303)
            return HTMLResponse(render(bank.variant, bank=bank, base=base(bid),
                                       error="We don't recognise that email."), status_code=401)

        user = data.verify_credentials(username, password)
        if not user:
            return HTMLResponse(render(bank.variant, bank=bank, base=base(bid),
                                       error="Invalid email or password."), status_code=401)
        return _begin_otp(request, bank, st, user, cfg, secrets)

    @app.get("/bank/{bid}/login-password", response_class=HTMLResponse)
    def login_password(bid: str, request: Request):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)
        if "pending_user" not in st:
            return RedirectResponse(base(bid), status_code=303)
        return HTMLResponse(render("two_step_pw", bank=bank, base=base(bid),
                                   username=st["pending_user"], error=None))

    @app.post("/bank/{bid}/login-password")
    def login_password_post(bid: str, request: Request, password: str = Form("")):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)
        username = st.get("pending_user", "")
        user = data.verify_credentials(username, password)
        if not user:
            return HTMLResponse(render("two_step_pw", bank=bank, base=base(bid),
                                       username=username, error="Invalid password."), status_code=401)
        return _begin_otp(request, bank, st, user, cfg, secrets)

    def _begin_otp(request, bank, st, user, cfg, secrets):
        code = data.generate_otp()
        st.update({"stage": "otp", "user": user.id, "otp": code,
                   "otp_exp": time.time() + cfg["otp_ttl_seconds"], "pending_user": None})
        request.session[bank.id] = st
        mailer.send_otp(to_addr=user.email, bank_name=bank.name, code=code,
                        backend=cfg["mail"]["backend"], cfg=cfg, secrets=secrets)
        return RedirectResponse(base(bank.id) + "otp", status_code=303)

    # --- OTP -------------------------------------------------------------------------
    @app.get("/bank/{bid}/otp", response_class=HTMLResponse)
    def otp_page(bid: str, request: Request):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)
        if st.get("stage") != "otp":
            return RedirectResponse(base(bid), status_code=303)
        email = data.USERS[st["user"]].email
        return HTMLResponse(render("otp", bank=bank, base=base(bid), email=email, error=None))

    @app.post("/bank/{bid}/otp")
    def otp_verify(bid: str, request: Request, otp: str = Form("")):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)
        if st.get("stage") != "otp":
            return RedirectResponse(base(bid), status_code=303)
        email = data.USERS[st["user"]].email
        if time.time() > st.get("otp_exp", 0):
            return HTMLResponse(render("otp", bank=bank, base=base(bid), email=email,
                                       error="Code expired. Please sign in again."), status_code=401)
        if (otp or "").strip() != st.get("otp"):
            return HTMLResponse(render("otp", bank=bank, base=base(bid), email=email,
                                       error="Incorrect code."), status_code=401)
        st["stage"] = "authed"
        request.session[bid] = st
        return RedirectResponse(base(bid) + "statements", status_code=303)

    # --- statements + PDF download ---------------------------------------------------
    @app.get("/bank/{bid}/statements", response_class=HTMLResponse)
    def statements(bid: str, request: Request):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)
        if st.get("stage") != "authed":
            return RedirectResponse(base(bid), status_code=303)
        user = data.USERS[st["user"]]
        return HTMLResponse(render("statements", bank=bank, base=base(bid),
                                   username=user.username, statements=data.statements_for(user)))

    @app.get("/bank/{bid}/statement/{sid}.pdf")
    def statement_download(bid: str, sid: str, request: Request):
        bank = require_bank(bid)
        if not bank:
            return HTMLResponse("unknown bank", status_code=404)
        st = state(request, bid)
        if st.get("stage") != "authed":
            return RedirectResponse(base(bid), status_code=303)
        user = data.USERS[st["user"]]
        match = next((s for s in data.statements_for(user) if s.id == sid), None)
        if not match:
            return HTMLResponse("no such statement", status_code=404)
        pdf = statement_pdf(bank.name, user.username, match.period, data.statement_rows(f"{bid}{sid}"))
        filename = f"{bank.id}_{match.id}.pdf"
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.get("/bank/{bid}/logout")
    def logout(bid: str, request: Request):
        request.session.pop(bid, None)
        return RedirectResponse(base(bid), status_code=303)

    @app.get("/")
    def index():
        return {"banks": list(BANKS), "hint": "open /bank/bank01/"}

    return app


app = create_app()
