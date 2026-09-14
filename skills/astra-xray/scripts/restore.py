#!/usr/bin/env python3
"""Put files back exactly as an astra-xray backup recorded them.

  restore.py BACKUP.zip --dry-run   # show what would change
  restore.py BACKUP.zip --yes       # restore; stops on conflicts
  restore.py BACKUP.zip --yes --force

A conflict is a file that changed after the edits were sealed (or a backup that was
never sealed). Before restoring, the current state is itself backed up, so a restore
can be undone too. Prints JSON. Exit codes: 0 done, 1 error, 2 conflicts need --force.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xray import archive  # noqa: E402


def plan_restore(manifest: dict, after: dict | None) -> list[dict]:
    after_files = (after or {}).get("files", {})
    steps = []
    for info in manifest["files"]:
        path = Path(info["path"])
        current = archive.sha256_path(path)
        sealed = after_files.get(info["path"], "missing") if after else "missing"
        if info["existed"]:
            if current == info["sha256"]:
                step = "unchanged"
            elif after is not None and current == sealed:
                step = "restore"
            else:
                step = "conflict"
        else:
            if current is None:
                step = "unchanged"
            elif after is not None and current == sealed:
                step = "delete"
            else:
                step = "conflict"
        steps.append({"path": info["path"], "step": step, "existed_before": info["existed"],
                      "reason": None if step != "conflict" else ("backup was never sealed" if after is None
                                                                  else "changed after the edits")})
    return steps


def write_back(info: dict, data: bytes) -> None:
    path = Path(info["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    if info.get("symlink_to"):
        if path.exists() and not path.is_symlink():
            path.unlink()
        if not path.is_symlink():
            os.symlink(info["symlink_to"], path)
        path = Path(os.path.realpath(path))
        path.parent.mkdir(parents=True, exist_ok=True)
    elif path.is_symlink():
        path.unlink()
    tmp = path.with_name(f".{path.name}.astra-xray-restore")
    tmp.write_bytes(data)
    os.chmod(tmp, info.get("mode", 0o644))
    os.replace(tmp, path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("backup")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true", help="required to change files")
    parser.add_argument("--force", action="store_true", help="also overwrite conflicting files")
    args = parser.parse_args(argv)
    backup = Path(args.backup).expanduser()

    try:
        archive.verify(backup)
        manifest, after = archive.load(backup)
        steps = plan_restore(manifest, after)
        conflicts = [s for s in steps if s["step"] == "conflict"]
        result = {"backup": str(backup), "steps": steps,
                  "counts": {k: sum(1 for s in steps if s["step"] == k) for k in ("restore", "delete", "conflict", "unchanged")}}
        if args.dry_run or not args.yes:
            result["dry_run"] = True
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if conflicts and not args.dry_run else 0
        if conflicts and not args.force:
            result["error"] = "conflicts found; review them, then rerun with --force to overwrite"
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2

        by_path = {info["path"]: info for info in manifest["files"]}
        touched = [s for s in steps if s["step"] in ("restore", "delete", "conflict")]
        pre_backup = None
        if touched:
            pre = archive.create([(s["path"], "modify") for s in touched], label=f"pre-restore-{backup.stem}")
            result["pre_restore_backup"] = pre["backup"]
            pre_backup = Path(pre["backup"])

        for step in touched:
            info = by_path[step["path"]]
            if info["existed"]:
                write_back(info, archive.read_member(backup, info["member"]))
            elif Path(info["path"]).exists() or Path(info["path"]).is_symlink():
                Path(info["path"]).unlink()

        failures = []
        for step in touched:
            info = by_path[step["path"]]
            now = archive.sha256_path(Path(info["path"]))
            expected = info["sha256"] if info["existed"] else None
            if now != expected:
                failures.append(info["path"])
        result["verified"] = not failures
        if pre_backup is not None:
            result["pre_restore_backup_seal"] = archive.seal(pre_backup)
        if failures:
            result["error"] = "some files do not match the backup after restore"
            result["failed"] = failures
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if failures else 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
