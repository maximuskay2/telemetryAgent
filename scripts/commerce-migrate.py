#!/usr/bin/env python3
"""Import today's JSON file store into the `legacy` org (C-J3, one-off).

Usage:
    DATABASE_URL=... python scripts/commerce-migrate.py --owner <clerk-user-id>
        [--email ...] [--name ...] [--data-dir ...]

Demo systems stay in the file store; the simulation route never touches
the database. Re-runs are idempotent. Prints per-stage counts as JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import the JSON file store into the legacy org."
    )
    parser.add_argument(
        "--owner", required=True,
        help="Clerk user id that will own the legacy org",
    )
    parser.add_argument("--email", default="")
    parser.add_argument("--name", default="")
    parser.add_argument(
        "--data-dir", default="",
        help="File-store root (default: $TA_DATA_DIR or ./data)",
    )
    args = parser.parse_args()

    from core.commerce import migrate as migrate_module

    try:
        result = migrate_module.migrate(
            data_dir=Path(args.data_dir) if args.data_dir else None,
            owner_external_id=args.owner,
            email=args.email,
            name=args.name,
        )
    except RuntimeError as exc:
        print(f"commerce-migrate: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
