#!/usr/bin/env python3
"""Back up files before astra-xray edits them.

  backup.py create --plan plan.json [--from-scan scan.json] [--label NAME]
  backup.py seal BACKUP.zip        # run right after the edits
  backup.py list

plan.json: {"modify": [paths], "create": [paths], "delete": [paths]}
--from-scan adds every instruction file the scan found, so nothing edited by accident is lost.
Prints JSON. Exit code 1 means no verified backup exists: do not edit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xray import archive  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--plan", required=True)
    create.add_argument("--from-scan")
    create.add_argument("--label", default="apply")
    seal = sub.add_parser("seal")
    seal.add_argument("backup")
    sub.add_parser("list")
    args = parser.parse_args(argv)

    try:
        if args.command == "create":
            plan = json.loads(Path(args.plan).expanduser().read_text(encoding="utf-8"))
            changes = [(p, action) for action in ("modify", "create", "delete") for p in plan.get(action, [])]
            if not changes:
                raise RuntimeError("plan lists no files")
            if args.from_scan:
                scan = json.loads(Path(args.from_scan).expanduser().read_text(encoding="utf-8"))
                changes += [(p, "surface") for p in scan.get("surface_files", [])]
            result = archive.create(changes, label=args.label)
        elif args.command == "seal":
            result = archive.seal(Path(args.backup).expanduser())
        else:
            result = archive.list_backups()
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
