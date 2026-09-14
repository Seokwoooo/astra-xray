"""SKILL.md frontmatter and agents/openai.yaml reading, matching codex-rs/skills/src/parser.rs.

Only the fields Codex puts in the skills list are read: name, description and
metadata.short-description. Values are collapsed to one line the same way Codex does.
"""

from __future__ import annotations

import re
from pathlib import Path

from .constants import MAX_SKILL_NAME_CHARS


def sanitize_single_line(raw: str) -> str:
    return " ".join(raw.split())


def extract_frontmatter(contents: str) -> tuple[str, str] | None:
    """Return (frontmatter, body) or None when the --- block is missing or empty."""
    lines = contents.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    collected = []
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            if not collected:
                return None
            return "\n".join(collected), "\n".join(lines[index + 1 :])
        collected.append(line)
    return None


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\n", " ").replace("\\\\", "\\")
    # Plain scalar: drop a trailing " # comment".
    return re.sub(r"\s+#.*$", "", value)


def _parse_mapping(frontmatter: str) -> dict:
    """Parse the small YAML subset skills use: scalars, block scalars, one nested map."""
    result: dict = {}
    lines = frontmatter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0] in " \t":
            continue
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        rest = rest.strip()
        if rest in ("", "|", ">", "|-", ">-", "|+", ">+"):
            block = []
            while index < len(lines) and (not lines[index].strip() or lines[index][0] in " \t"):
                block.append(lines[index])
                index += 1
            if rest == "" and any(re.match(r"^\s+[\w-]+\s*:", b) for b in block):
                nested = {}
                for b in block:
                    nkey, nsep, nrest = b.strip().partition(":")
                    if nsep:
                        nested[nkey.strip()] = _unquote(nrest)
                result[key] = nested
            else:
                result[key] = " ".join(b.strip() for b in block)
            continue
        value = _unquote(rest)
        # Plain multi-line scalars continue on more-indented lines.
        while index < len(lines) and lines[index][:1] in (" ", "\t") and lines[index].strip():
            value += " " + lines[index].strip()
            index += 1
        result[key] = value
    return result


def read_skill(path: Path) -> dict:
    """Read one SKILL.md. Returns name, description, short_description, body, error."""
    info = {
        "path": str(path),
        "name": path.parent.name,
        "description": "",
        "short_description": None,
        "body": "",
        "raw_bytes": 0,
        "error": None,
    }
    try:
        data = path.read_bytes()
    except OSError as exc:
        info["error"] = f"unreadable: {exc.strerror or exc}"
        return info
    info["raw_bytes"] = len(data)
    contents = data.decode("utf-8", errors="replace")
    extracted = extract_frontmatter(contents)
    if extracted is None:
        info["error"] = "missing YAML frontmatter delimited by ---"
        info["body"] = contents
        return info
    frontmatter, body = extracted
    info["body"] = body
    fields = _parse_mapping(frontmatter)
    name = sanitize_single_line(str(fields.get("name") or ""))
    if name:
        info["name"] = name
    info["description"] = sanitize_single_line(str(fields.get("description") or ""))
    metadata = fields.get("metadata")
    if isinstance(metadata, dict):
        short = sanitize_single_line(str(metadata.get("short-description") or ""))
        info["short_description"] = short or None
    if not name:
        info["error"] = "missing field `name`"
    elif len(info["name"]) > MAX_SKILL_NAME_CHARS:
        info["error"] = f"invalid name: exceeds maximum length of {MAX_SKILL_NAME_CHARS} characters"
    elif not info["description"]:
        info["error"] = "missing field `description`"
    return info


def implicit_invocation_allowed(skill_dir: Path) -> bool:
    """False when agents/openai.yaml sets policy.allow_implicit_invocation: false."""
    yaml_path = skill_dir / "agents" / "openai.yaml"
    try:
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    in_policy = False
    for line in text.splitlines():
        if re.match(r"^policy\s*:", line):
            in_policy = True
            continue
        if in_policy and line[:1] not in (" ", "\t") and line.strip():
            in_policy = False
        if in_policy:
            match = re.match(r"^\s+allow_implicit_invocation\s*:\s*(\S+)", line)
            if match:
                return match.group(1).strip("'\"").lower() != "false"
    return True
