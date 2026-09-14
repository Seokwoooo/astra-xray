"""Read the host skills catalog from local Codex session logs.

Only ``world_state.state.host_skills`` and a few metadata fields are trusted.
Conversation content is ignored.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

LOCATOR_KINDS = ("file", "executor package", "orchestrator package", "custom resource")
ROOT_LINE = re.compile(r"^- `(r\d+)` = `(.*)`$")
OMISSION_LINE = re.compile(r"^- (\d+) additional skills? omitted")


def recent_session_files(home: Path, limit: int = 200) -> list[Path]:
    files = []
    for folder in (home / "sessions",):
        if folder.is_dir():
            files.extend(folder.rglob("rollout-*.jsonl"))
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def _skills_body_from_record(record: dict) -> str | None:
    if record.get("type") == "world_state":
        body = (((record.get("payload") or {}).get("state") or {}).get("host_skills") or {}).get("body")
        if isinstance(body, str) and "### Available skills" in body:
            return body
    return None


def timestamp_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def cwd_matches(info: dict, cwd: Path) -> bool:
    raw = info.get("cwd")
    if not raw:
        return False
    try:
        return Path(raw).expanduser().resolve() == cwd.expanduser().resolve()
    except OSError:
        return str(Path(raw).expanduser()) == str(cwd.expanduser())


def catalog_is_fresh(info: dict, not_before: float | None) -> bool:
    if not_before is None:
        return True
    captured = timestamp_epoch(info.get("skills_timestamp") or info.get("timestamp"))
    return captured is not None and captured >= not_before


def read_session(path: Path) -> dict | None:
    info = {
        "path": str(path),
        "cli_version": None,
        "model": None,
        "cwd": None,
        "timestamp": None,
        "skills_timestamp": None,
        "skills_body": None,
    }
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return None
    with handle:
        for line in handle:
            if not any(tag in line for tag in ('"session_meta"', '"turn_context"', '"world_state"')):
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            payload = record.get("payload") or {}
            kind = record.get("type")
            if kind == "session_meta":
                info["cli_version"] = payload.get("cli_version")
                info["cwd"] = payload.get("cwd")
                info["timestamp"] = payload.get("timestamp") or record.get("timestamp")
            elif kind == "turn_context" and payload.get("model"):
                info["model"] = payload["model"]
            body = _skills_body_from_record(record)
            if body:
                info["skills_body"] = body  # keep the latest trusted catalog in the file
                info["skills_timestamp"] = record.get("timestamp") or info["timestamp"]
    return info if info["skills_body"] else None


def find_session(
    home: Path,
    explicit: str | None = None,
    cwd: Path | None = None,
    not_before: float | None = None,
) -> dict | None:
    """Return a trusted catalog for this working directory.

    The source session model is deliberately irrelevant: its catalog identifies the
    host skills, while the scanner separately simulates the requested target model.
    Explicit paths are returned for forensic use and annotated by the caller.
    """
    if explicit:
        info = read_session(Path(explicit).expanduser())
        if info:
            info["selection"] = "explicit"
        return info
    for path in recent_session_files(home):
        info = read_session(path)
        if not info:
            continue
        if cwd is not None and not cwd_matches(info, cwd):
            continue
        if not catalog_is_fresh(info, not_before):
            continue
        info["selection"] = "auto"
        return info
    return None


def parse_skills_body(body: str) -> dict:
    roots, entries, omitted = [], [], 0
    section = None
    intro = "aliased" if "skill roots table" in body else "absolute"
    for line in body.splitlines():
        if line.startswith("### Skill roots"):
            section = "roots"
            continue
        if line.startswith("### Available skills"):
            section = "skills"
            continue
        if line.startswith("#"):
            section = None
            continue
        if section == "roots":
            match = ROOT_LINE.match(line)
            if match:
                roots.append((match.group(1), match.group(2)))
        elif section == "skills" and line.startswith("- "):
            omission = OMISSION_LINE.match(line)
            if omission:
                omitted = int(omission.group(1))
                continue
            entry = parse_entry(line)
            if entry:
                entries.append(entry)
    root_map = dict(roots)
    for entry in entries:
        match = re.match(r"^(r\d+)/(.*)$", entry["locator"])
        if match and match.group(1) in root_map:
            entry["path"] = root_map[match.group(1)].rstrip("/") + "/" + match.group(2)
            entry["alias"] = match.group(1)
        else:
            entry["path"] = entry["locator"]
            entry["alias"] = None
    return {"format": intro, "roots": roots, "entries": entries, "omission_marker": omitted}


def parse_entry(line: str) -> dict | None:
    head = re.match(r"^- (\S+): ", line)
    if not head:
        return None
    rest = line[head.end() :]
    best = (-1, None)
    for kind in LOCATOR_KINDS:
        index = rest.rfind(f"({kind}: ")
        if index > best[0]:
            best = (index, kind)
    index, kind = best
    if index < 0 or not rest.endswith(")"):
        return None
    description = rest[:index]
    if description.endswith(" "):
        description = description[:-1]
    locator = rest[index + len(kind) + 3 : -1]
    return {"name": head.group(1), "description": description, "kind": kind, "locator": locator, "line": line}
