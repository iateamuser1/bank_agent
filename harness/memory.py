"""Working memory (run journal) and long-term memory (per-bank recipe cache).

Journal: append-only, redacted — the resumable record of what happened.
RecipeCache: what was learned about a bank (does login need a trigger click? two-step?) so
later users/runs replay deterministically instead of re-exploring. Never stores secrets.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


class Journal:
    def __init__(self, redactor):
        self.path = _ROOT / "journal.jsonl"
        self.redactor = redactor

    def write(self, **event) -> None:
        event["ts"] = round(time.time(), 3)
        line = self.redactor.scrub(json.dumps(event, ensure_ascii=False))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class RecipeCache:
    def __init__(self, bank_id: str):
        self.dir = _ROOT / "recipes"
        self.dir.mkdir(exist_ok=True)
        self.path = self.dir / f"{bank_id}.json"

    def load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self, recipe: dict) -> None:
        self.path.write_text(json.dumps(recipe, indent=2), encoding="utf-8")
