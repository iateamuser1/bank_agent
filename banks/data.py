"""The bank's own server-side data: registered users, OTP generation, and statements.

This is the *bank's* record of its customers — deliberately separate from the automation's
vault. For the login+OTP flow to succeed, the active user here mirrors the vault's active
user (iateamuser1). user2..user5 are placeholders so each bank has the required 5 users.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password: str
    email: str          # where the OTP is sent


# 5 registered users per bank. Only user1 is a real, reachable mailbox.
USERS: dict[str, User] = {
    "user1": User("user1", "iateamuser1@gmail.com", "Testing@123", "iateamuser1@gmail.com"),
    "user2": User("user2", "iateamuser2@example.com", "Testing@123", "iateamuser2@example.com"),
    "user3": User("user3", "iateamuser3@example.com", "Testing@123", "iateamuser3@example.com"),
    "user4": User("user4", "iateamuser4@example.com", "Testing@123", "iateamuser4@example.com"),
    "user5": User("user5", "iateamuser5@example.com", "Testing@123", "iateamuser5@example.com"),
}


def verify_credentials(username: str, password: str) -> User | None:
    for user in USERS.values():
        if user.username.lower() == (username or "").strip().lower() and user.password == password:
            return user
    return None


def find_user_by_username(username: str) -> User | None:
    for user in USERS.values():
        if user.username.lower() == (username or "").strip().lower():
            return user
    return None


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


@dataclass(frozen=True)
class Statement:
    id: str
    period: str         # e.g. "May 2026"
    stmt_date: str      # ISO date, used to pick the latest


def statements_for(user: User, today: date | None = None) -> list[Statement]:
    """Four most-recent monthly statements, newest first."""
    today = today or date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(4):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        d = date(y, m, 28)
        out.append(Statement(id=f"{y}{m:02d}", period=d.strftime("%B %Y"), stmt_date=d.isoformat()))
    return out          # already newest-first


def statement_rows(seed: str) -> list[tuple[str, str, str]]:
    rng = random.Random(seed)
    merchants = ["Grocery Mart", "Coffee House", "Electric Co.", "Salary Credit", "Book Store", "Fuel Stop"]
    rows = []
    for i in range(6):
        amt = rng.randint(-8000, 12000) / 100
        sign = "+" if amt >= 0 else "-"
        rows.append((f"{i+1:02d} of period", rng.choice(merchants), f"{sign}${abs(amt):,.2f}"))
    return rows
