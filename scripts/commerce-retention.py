#!/usr/bin/env python3
"""Retention sweep for commerce rows (C-J5; run from cron, not the API).

Deletes audit rows older than --days (default 90, floor 7) and trims
system profile history to --keep versions per system (default 20,
floor 5) via SECURITY DEFINER functions (the app role cannot see
across orgs). Prints counts as JSON. Needs DATABASE_URL.
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
        description="Sweep old audit rows + profile versions."
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="audit rows older than this are deleted (floor 7)",
    )
    parser.add_argument(
        "--keep", type=int, default=20,
        help="profile versions kept per system (floor 5)",
    )
    args = parser.parse_args()

    from core.commerce import db as db_module
    from core.commerce import repo as repo_module

    if not db_module.using_postgres():
        print(
            "commerce-retention: DATABASE_URL is not set",
            file=sys.stderr,
        )
        return 1
    store = repo_module.get_store()
    audit = store.sweep_audit(args.days)
    versions = store.sweep_versions(args.keep)
    print(json.dumps(
        {"audit_deleted": audit, "versions_deleted": versions}
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
