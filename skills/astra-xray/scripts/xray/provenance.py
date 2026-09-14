"""Read local ownership evidence. A user installation directory is not authorship."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .paths import is_within, local_key, path_key
from .frontmatter import read_skill

MANAGED_KINDS = {"system", "admin", "plugin"}
UPSTREAM_FAMILY = re.compile(r"(?:^|[:/_.-])(?:playwright|superpowers|puppeteer|puppetter)(?:$|[:/_.-])", re.I)


def _result(kind, evidence, source=None):
    return {"kind": kind, "editable": kind == "local", "evidence": evidence, "source": source}


def _json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def classify(path: Path, root_kind: str = "user", local_skills=()) -> dict:
    resolved = path.resolve()
    normalized = path_key(str(resolved))
    if root_kind in MANAGED_KINDS or any(part in normalized for part in
                                        ("/skills/.system/", "/plugins/cache/")):
        return _result("managed", "system, admin or plugin-owned installation")
    name = read_skill(path)["name"]
    if UPSTREAM_FAMILY.search(name) or UPSTREAM_FAMILY.search(path.parent.name) or "/superpowers/" in normalized.lower():
        return _result("upstream", "protected upstream family: Playwright, Superpowers or Puppeteer")

    # Bind lock records to the installation root as well as the name. A same-name
    # project skill must not inherit ownership from an unrelated global install.
    for parent in path.parents:
        for lock, roots in (
            (parent / ".skill-lock.json", [parent / "skills"]),
            (parent / "skills-lock.json", [parent / ".agents" / "skills", parent / ".codex" / "skills"]),
        ):
            if not lock.is_file():
                continue
            skills = _json(lock).get("skills", {})
            if not isinstance(skills, dict):
                continue
            for name, entry in skills.items():
                if not isinstance(entry, dict):
                    continue
                if not any(is_within(str(path), str(root / name)) for root in roots):
                    continue
                if entry.get("source") or entry.get("sourceUrl"):
                    return _result("upstream", f"installer lock: {lock}", entry.get("source") or entry.get("sourceUrl"))

    # A linked checkout (including Superpowers) remains maintained at its source.
    # Ordinary GitHub links in a skill's instructions are not ownership evidence.
    for parent in resolved.parents:
        if (parent / ".git").exists():
            if not is_within(str(path), str(parent)):
                return _result("upstream", f"linked Git checkout: {parent}")
            break
    evidence_files = [path.parent / name for name in
                      ("LICENSE", "LICENSE.txt", "LICENSE.md", "NOTICE.txt", "NOTICE", ".skill-metadata.json")]
    evidence_files += [path]
    for candidate in evidence_files:
        if candidate.suffix == ".json":
            metadata = _json(candidate)
            for key in ("source", "sourceUrl", "upstream", "repository", "repo"):
                if metadata.get(key):
                    return _result("upstream", f"publisher metadata: {candidate}", metadata[key])
        try:
            text = candidate.read_text(encoding="utf-8-sig", errors="replace")[:16000]
        except OSError:
            continue
        if re.search(r"(?im)^.*copyright[^\n]*(?:OpenAI|Microsoft|Anthropic|Vercel)\b", text):
            return _result("upstream", f"publisher copyright: {candidate}")
        if re.search(r"(?im)^\s*(?:source|upstream|repository|repo|license)\s*:\s*.*"
                     r"(?:github\.com/|skills\.sh/|OpenAI|Microsoft|Anthropic|Vercel)", text):
            return _result("upstream", f"publisher metadata: {candidate}")

    if local_key(str(path)) in {local_key(str(p)) for p in local_skills}:
        return _result("local", "authorship verified by the operator for this exact path")
    return _result("unverified", "no conclusive ownership record; inspect authorship before editing")
