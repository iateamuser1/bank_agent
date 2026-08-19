"""The 20 mock bank portals.

Each bank is one instance of the same app, distinguished by id, display name, and — the
important part — a **login-layout variant**. The five variants place the login form in a
different spot so the automation's form-detection engine (see auto-login SKILL) is genuinely
exercised: header, centered card, modal behind a button, a two-step username→password flow,
and a form nested in an iframe.
"""

from dataclasses import dataclass

# The five ways a login form can hide on a page.
LAYOUT_VARIANTS = ["inline_top", "center_card", "modal", "two_step", "iframe"]

_BANK_NAMES = [
    "Meridian", "Northwind", "Silverpeak", "Harbour", "Ironwood",
    "Blue Ridge", "Coppertree", "Fairhaven", "Granite", "Lakeshore",
    "Maplewood", "Oakmont", "Pinnacle", "Riverstone", "Summit",
    "Thornfield", "Westbrook", "Cedar Valley", "Evergreen", "Highland",
]


@dataclass(frozen=True)
class Bank:
    id: str
    name: str          # e.g. "Meridian Bank"
    variant: str       # one of LAYOUT_VARIANTS


def _build() -> dict[str, Bank]:
    banks = {}
    for i, base in enumerate(_BANK_NAMES, start=1):
        bid = f"bank{i:02d}"
        banks[bid] = Bank(id=bid, name=f"{base} Bank", variant=LAYOUT_VARIANTS[i % len(LAYOUT_VARIANTS)])
    return banks


BANKS: dict[str, Bank] = _build()


def bank_url(base: str, bid: str) -> str:
    return f"{base.rstrip('/')}/bank/{bid}/"
