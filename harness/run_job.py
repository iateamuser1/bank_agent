"""CLI: run one (bank, user) job.

    python -m bank_agent.harness.run_job --bank bank01 --user user1
    python -m bank_agent.harness.run_job --bank bank03 --user user1 --headed
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml

from ..banks.registry import BANKS
from .agent import run_job

_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser(description="Log in, pass OTP, download the latest statement.")
    ap.add_argument("--bank", required=True, choices=list(BANKS))
    ap.add_argument("--user", default="user1")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load((_ROOT / "config.yaml").read_text(encoding="utf-8"))
    result = asyncio.run(run_job(args.bank, args.user, cfg, headless=not args.headed))

    print(f"[{result.status}] {result.bank_id}/{result.user_id} "
          f"(stage: {result.stage_reached}) — {result.reason}")
    if result.statement_path:
        print(f"  statement: {result.statement_path}")


if __name__ == "__main__":
    main()
