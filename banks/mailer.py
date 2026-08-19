"""Send the OTP email.

Two backends, chosen in config.yaml:
- local: write the message as JSON into a maildir the reader can read (offline, deterministic).
- gmail: send via Gmail SMTP over SSL (needs the account's App Password).

Either way the OTP reader on the other side finds the code — the automation never depends on
which backend was used.
"""

from __future__ import annotations

import json
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path


def _subject(bank_name: str) -> str:
    return f"{bank_name} verification code"


def _body(bank_name: str, code: str) -> str:
    return (
        f"Your {bank_name} one-time verification code is {code}.\n"
        f"It expires in 5 minutes. Do not share it with anyone."
    )


def send_otp(*, to_addr: str, bank_name: str, code: str, backend: str, cfg: dict, secrets: dict) -> None:
    if backend == "local":
        _send_local(to_addr, bank_name, code, Path(cfg["mail"]["maildir"]))
    elif backend == "gmail":
        _send_gmail(to_addr, bank_name, code, cfg, secrets)
    else:
        raise ValueError(f"unknown mail backend: {backend}")


def _send_local(to_addr: str, bank_name: str, code: str, maildir: Path) -> None:
    box = maildir / to_addr.replace("/", "_")
    box.mkdir(parents=True, exist_ok=True)
    msg = {
        "from": f"no-reply@{bank_name.split()[0].lower()}.example",
        "to": to_addr,
        "subject": _subject(bank_name),
        "body": _body(bank_name, code),
        "bank": bank_name,
        "ts": time.time(),
    }
    (box / f"{int(msg['ts'] * 1000)}.json").write_text(json.dumps(msg), encoding="utf-8")


def _send_gmail(to_addr: str, bank_name: str, code: str, cfg: dict, secrets: dict) -> None:
    gmail = secrets["users"][0]["gmail_address"]
    app_password = secrets["users"][0]["gmail_app_password"]
    msg = EmailMessage()
    msg["Subject"] = _subject(bank_name)
    msg["From"] = gmail
    msg["To"] = to_addr
    msg.set_content(_body(bank_name, code))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(cfg["mail"]["smtp_host"], cfg["mail"]["smtp_port"], context=context) as s:
        s.login(gmail, app_password)
        s.send_message(msg)
