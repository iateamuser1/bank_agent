"""Secret vault + redaction.

Two responsibilities that together enforce the 'secrets never leak' rule:
- load per-user credentials and service keys from secrets/vault.yaml;
- a Redactor that scrubs every known secret (and runtime secrets like the OTP) out of any
  string before it reaches a log, journal entry, screenshot name, or LLM prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class UserSecret:
    id: str
    portal_username: str
    portal_password: str
    gmail_address: str
    gmail_app_password: str


class Vault:
    def __init__(self, path: Path | None = None):
        self._data = yaml.safe_load((path or _ROOT / "secrets" / "vault.yaml").read_text(encoding="utf-8"))

    def user(self, user_id: str) -> UserSecret:
        for u in self._data["users"]:
            if u["id"] == user_id:
                return UserSecret(u["id"], u["portal_username"], u["portal_password"],
                                  u["gmail_address"], u.get("gmail_app_password", ""))
        raise KeyError(f"user {user_id} not in vault")

    def azure(self) -> dict:
        return self._data.get("azure_foundry", {})

    def all_static_secrets(self) -> list[str]:
        """Every secret string known at load time — used to seed the redactor."""
        out = []
        for u in self._data["users"]:
            out += [u.get("portal_password", ""), u.get("gmail_app_password", "")]
        out.append(self._data.get("azure_foundry", {}).get("api_key", ""))
        return [s for s in out if s]


class Redactor:
    """Replaces known secrets with '****'. Register short-lived secrets (OTP) at runtime."""

    def __init__(self, secrets: list[str]):
        self._secrets = set(s for s in secrets if s)

    def add(self, secret: str) -> None:
        if secret:
            self._secrets.add(secret)

    def scrub(self, text: str) -> str:
        if not text:
            return text
        for s in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(s, "****")
        return text
