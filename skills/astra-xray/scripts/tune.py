#!/usr/bin/env python3
"""Preview or apply reviewed description edits. No model calls or network access.

  tune.py --plan plan.json          # validate every edit and print diffs
  tune.py --plan plan.json --apply  # verify backup, edit, verify bytes, seal

Plan: {"local_skills": [absolute SKILL.md paths with verified local authorship],
       "edits": [{"path": "...", "sha256": "...", "description": "...", "reason": "..."}]}
The agent writes the proposed text after reviewing purpose and trigger boundaries.
This helper never invents replacement descriptions or changes model configuration.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from xray import archive, budget  # noqa: E402
from xray.constants import MAX_CATALOG_DESCRIPTION_CHARS  # noqa: E402
from xray.frontmatter import read_skill, replace_description  # noqa: E402
from xray.paths import local_key  # noqa: E402
from xray.provenance import classify  # noqa: E402


def prepare(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get("edits"), list) or not plan["edits"]:
        raise ValueError("plan must contain a non-empty edits list")
    local = plan.get("local_skills", [])
    if not isinstance(local, list) or any(not isinstance(p, str) for p in local):
        raise ValueError("local_skills must be a list of verified local SKILL.md paths")
    prepared, seen = [], set()
    for edit in plan["edits"]:
        path = Path(edit["path"]).expanduser()
        if not path.is_absolute() or path.name != "SKILL.md" or not path.is_file():
            raise ValueError(f"not an existing absolute SKILL.md path: {path}")
        key = local_key(str(path))
        if key in seen:
            raise ValueError(f"duplicate edit for {path}")
        seen.add(key)
        owner = classify(path, local_skills=local)
        if not owner["editable"]:
            raise ValueError(f"{path}: {owner['kind']}; {owner['evidence']}")
        before = path.read_bytes()
        if edit.get("sha256") != archive.sha256_bytes(before):
            raise ValueError(f"file changed since review: {path}")
        if not isinstance(edit.get("reason"), str) or not edit["reason"].strip():
            raise ValueError(f"missing review reason: {path}")
        info = read_skill(path)
        if info["error"]:
            raise ValueError(f"{path}: {info['error']}")
        desc = edit["description"]
        if not isinstance(desc, str):
            raise ValueError(f"description must be a string: {path}")
        if len(desc) > MAX_CATALOG_DESCRIPTION_CHARS:
            raise ValueError(f"proposed description exceeds the {MAX_CATALOG_DESCRIPTION_CHARS}-character catalog cap: {path}")
        after = replace_description(before, desc)
        if info["description"] == desc:
            raise ValueError(f"description is unchanged: {path}; record a keep decision instead")
        prepared.append({"path": path, "before": before, "after": after,
                         "old_description": info["description"], "description": desc, "reason": edit["reason"]})
    return prepared


def write_bytes(path: Path, data: bytes):
    # Resolve existing links to keep the installed link intact.
    path = path.resolve()
    mode = path.stat().st_mode & 0o777
    fd, temp = tempfile.mkstemp(prefix=".astra-xray-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    backup = None
    written = []
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8-sig"))
        prepared = prepare(plan)  # Validate the entire batch before any backup or edit.
        result = {"ok": True, "applied": False, "files": [], "description_chars_saved": 0,
                  "description_estimated_tokens_saved": 0}
        for item in prepared:
            result["files"].append({"path": str(item["path"]), "reason": item["reason"],
                                    "before_chars": len(item["old_description"]), "after_chars": len(item["description"]),
                                    "diff": "".join(difflib.unified_diff(
                                        item["before"].decode("utf-8-sig").splitlines(True),
                                        item["after"].decode("utf-8-sig").splitlines(True),
                                        fromfile=str(item["path"]), tofile=str(item["path"])))})
            result["description_chars_saved"] += len(item["old_description"]) - len(item["description"])
            result["description_estimated_tokens_saved"] += budget.approx_tokens(item["old_description"]) - budget.approx_tokens(item["description"])
        if args.apply:
            backup = archive.create([(str(item["path"]), "modify") for item in prepared], label="descriptions")
            result["backup"] = backup
            # Recheck all files after backup, before the first write.
            for item in prepared:
                if item["path"].read_bytes() != item["before"]:
                    raise ValueError(f"file changed during backup: {item['path']}")
            for item in prepared:
                if item["path"].read_bytes() != item["before"]:
                    raise ValueError(f"file changed during apply: {item['path']}")
                write_bytes(item["path"], item["after"])
                written.append(item)
                if item["path"].read_bytes() != item["after"]:
                    raise RuntimeError(f"write verification failed: {item['path']}")
            result["seal"] = archive.seal(Path(backup["backup"]))
            result["applied"] = True
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        # Roll back only bytes this process wrote. Preserve concurrent external edits.
        unresolved = []
        for item in reversed(written):
            try:
                if item["path"].read_bytes() == item["after"]:
                    write_bytes(item["path"], item["before"])
                else:
                    unresolved.append(str(item["path"]))
            except OSError:
                unresolved.append(str(item["path"]))
        result = {"ok": False, "applied": False, "error": str(exc), "unresolved": unresolved}
        if backup:
            result["backup"] = backup
            try:
                result["seal"] = archive.seal(Path(backup["backup"]))
            except OSError as seal_error:
                result["seal_error"] = str(seal_error)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
