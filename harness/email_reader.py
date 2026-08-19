"""Read the OTP from the user's mailbox.

Backends:
- local : read the maildir the mock banks write to (offline, deterministic).
- gmail : IMAP over SSL against Gmail using the App Password (the production path).

Both return the OTP for a specific bank + recipient, newer than `since_ts`, using the LLM to
pull the code out of the message body.
"""

from __future__ import annotations

import email
import glob
import imaplib
import json
import time
from email.utils import parsedate_to_datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# `since_ts` is read off the local clock; a message's Date header is stamped by Gmail's.
# Allow for the two disagreeing so a genuinely new mail is never discarded as stale.
_CLOCK_SKEW_S = 120


class OtpReader:
    def __init__(self, cfg: dict, vault, llm):
        self.cfg = cfg
        self.vault = vault
        self.llm = llm
        self.backend = cfg["mail"]["backend"]

    def fetch_otp(self, *, bank_name: str, user_id: str, since_ts: float,
                  attempts: int = 20, delay: float = 0.5) -> str | None:
        """Poll the mailbox until the code arrives (or attempts run out)."""
        for _ in range(attempts):
            code = self._read_once(bank_name=bank_name, user_id=user_id, since_ts=since_ts)
            if code:
                return code
            time.sleep(delay)
        return None

    # --- backends --------------------------------------------------------------------
    def _read_once(self, *, bank_name, user_id, since_ts) -> str | None:
        if self.backend == "local":
            return self._read_local(bank_name, user_id, since_ts)
        return self._read_gmail(bank_name, user_id, since_ts)

    def _read_local(self, bank_name, user_id, since_ts) -> str | None:
        to_addr = self.vault.user(user_id).gmail_address
        box = _ROOT / self.cfg["mail"]["maildir"] / to_addr.replace("/", "_")
        newest, newest_ts = None, since_ts
        for f in glob.glob(str(box / "*.json")):
            msg = json.loads(Path(f).read_text(encoding="utf-8"))
            if msg["bank"] == bank_name and msg["ts"] >= newest_ts:
                newest, newest_ts = msg, msg["ts"]
        if newest:
            return self.llm.extract_otp(newest["body"])
        return None

    def _read_gmail(self, bank_name, user_id, since_ts) -> str | None:
        user = self.vault.user(user_id)
        with imaplib.IMAP4_SSL(self.cfg["mail"]["imap_host"]) as im:
            im.login(user.gmail_address, user.gmail_app_password)
            im.select("INBOX")
            typ, ids = im.search(None, '(UNSEEN SUBJECT "%s")' % bank_name.split()[0])
            if typ != "OK":
                return None
            for msg_id in reversed(ids[0].split()):
                # PEEK, not RFC822: fetching must not set \Seen. Otherwise a message whose
                # code fails to extract is consumed on the first read and the polling loop
                # can never look at it again.
                typ, raw = im.fetch(msg_id, "(BODY.PEEK[])")
                if typ != "OK" or not raw or not raw[0]:
                    continue
                message = email.message_from_bytes(raw[0][1])
                # Since PEEK leaves messages unseen, an OTP from an earlier run would stay
                # in the search results forever. Drop anything predating this attempt.
                sent = _sent_ts(message)
                if sent is not None and sent < since_ts - _CLOCK_SKEW_S:
                    continue
                code = self.llm.extract_otp(_plain_text(message))
                if code:
                    im.store(msg_id, "+FLAGS", "\\Seen")  # consume only on success
                    return code
        return None


def _sent_ts(message) -> float | None:
    """Epoch seconds from the message's Date header; None if absent or unparseable."""
    raw = message.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).timestamp()
    except (TypeError, ValueError):
        return None


def _plain_text(message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(errors="ignore")
        return ""
    return message.get_payload(decode=True).decode(errors="ignore")
