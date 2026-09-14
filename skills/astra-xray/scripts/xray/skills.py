"""Skill roots and SKILL.md discovery, following codex-rs/ext/skills/src/host_roots.rs and loader/."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import constants as C
from .agents_md import find_project_root
from .config import get
from .frontmatter import implicit_invocation_allowed, read_skill
from .paths import local_key
from .provenance import classify

SCOPE_RANK = {"system": 0, "admin": 1, "repo": 2, "user": 3}


def _plugin_roots(home: Path, cfg: dict) -> list[dict]:
    roots = []
    plugins = get(cfg, "plugins", {}) or {}
    for key, settings in plugins.items():
        if not isinstance(settings, dict) or settings.get("enabled") is not True or "@" not in key:
            continue
        name, marketplace = key.split("@", 1)
        base = home / "plugins" / "cache" / marketplace / name
        try:
            versions = [p for p in base.iterdir() if p.is_dir()]
        except OSError:
            continue
        if not versions:
            continue
        version = max(versions, key=lambda p: p.stat().st_mtime)
        namespace, skill_paths = name, []
        for manifest in (".codex-plugin/plugin.json", ".claude-plugin/plugin.json"):
            try:
                data = json.loads((version / manifest).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            namespace = data.get("name") or name
            declared = (data.get("paths") or {}).get("skills") if isinstance(data.get("paths"), dict) else data.get("skills")
            if isinstance(declared, str):
                declared = [declared]
            skill_paths = [version / p for p in declared or [] if isinstance(p, str)]
            break
        if not skill_paths and (version / "skills").is_dir():
            skill_paths = [version / "skills"]
        for path in sorted(skill_paths):
            roots.append({"path": str(path), "scope": "user", "kind": "plugin", "namespace": namespace, "plugin": key})
    return roots


def skill_roots(cwd: Path, home: Path, cfg: dict) -> list[dict]:
    markers = get(cfg, "project_root_markers", C.DEFAULT_PROJECT_ROOT_MARKERS)
    project_root = find_project_root(cwd, markers if isinstance(markers, list) else C.DEFAULT_PROJECT_ROOT_MARKERS)
    between = [cwd]
    if project_root is not None:
        cursor = cwd
        while cursor != project_root and cursor.parent != cursor:
            cursor = cursor.parent
            between.append(cursor)

    roots = []
    for directory in between:  # project config layers, closest first
        roots.append({"path": str(directory / ".codex" / "skills"), "scope": "repo", "kind": "repo-codex"})
    roots.append({"path": str(home / "skills"), "scope": "user", "kind": "user-deprecated"})
    roots.append({"path": str(Path.home() / ".agents" / "skills"), "scope": "user", "kind": "user"})
    roots.append({"path": str(home / "skills" / ".system"), "scope": "system", "kind": "system"})
    roots.append({"path": "/etc/codex/skills", "scope": "admin", "kind": "admin"})
    roots.extend(_plugin_roots(home, cfg))
    for directory in reversed(between):  # repo .agents/skills, project root first
        roots.append({"path": str(directory / ".agents" / "skills"), "scope": "repo", "kind": "repo"})

    seen, unique = set(), []
    for root in roots:
        if root["path"] in seen or not Path(root["path"]).is_dir():
            continue
        seen.add(root["path"])
        root["order"] = len(unique)
        unique.append(root)
    return unique


def discover_skill_files(root: Path, follow_symlinks: bool) -> list[Path]:
    found, dirs_seen = [], 0
    stack = [(root, 0)]
    visited = set()
    while stack:
        directory, depth = stack.pop()
        try:
            real = directory.resolve()
        except OSError:
            continue
        if real in visited:
            continue
        visited.add(real)
        dirs_seen += 1
        if dirs_seen > C.MAX_SKILL_DIRS_PER_ROOT:
            break
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.name == "SKILL.md" and entry.is_file():
                found.append(path)
            elif entry.is_dir(follow_symlinks=follow_symlinks) and not entry.name.startswith("."):
                if depth + 1 <= C.MAX_SCAN_DEPTH:
                    stack.append((path, depth + 1))
    return sorted(found)


def _disabled_paths(cfg: dict) -> set[str]:
    disabled = set()
    for rule in get(cfg, "skills.config", []) or []:
        if isinstance(rule, dict) and rule.get("enabled") is False and rule.get("path"):
            try:
                disabled.add(local_key(rule["path"]))
            except OSError:
                disabled.add(rule["path"])
    return disabled


def inventory(cwd: Path, home: Path, cfg: dict, local_skills=()) -> dict:
    roots = skill_roots(cwd, home, cfg)
    disabled = _disabled_paths(cfg)
    skills = []
    seen = set()
    for root in roots:
        files = discover_skill_files(Path(root["path"]), follow_symlinks=root["scope"] != "system")
        for path in files:
            identity = (root.get("namespace"), local_key(str(path)))
            if identity in seen:
                continue
            seen.add(identity)
            info = read_skill(path)
            base_name = info["name"]
            info["name"] = f"{root['namespace']}:{base_name}" if root.get("namespace") else base_name
            try:
                resolved = str(path.resolve())
            except OSError:
                resolved = str(path)
            info.update(
                root=root["path"],
                scope=root["scope"],
                root_kind=root["kind"],
                alias_root=root["path"],
                alias_root_order=root["order"],
                enabled=local_key(resolved) not in disabled and local_key(str(path)) not in disabled,
                implicit=implicit_invocation_allowed(path.parent),
                body_lines=info["body"].count("\n") + 1 if info["body"] else 0,
                provenance=classify(path, root["kind"], local_skills),
            )
            info.pop("body", None)
            skills.append(info)

    names: dict = {}
    for skill in skills:
        names.setdefault(skill["name"], []).append(skill["path"])
    duplicates = {name: paths for name, paths in names.items() if len(paths) > 1}
    return {"roots": roots, "skills": skills, "duplicates": duplicates}


def listed_entries(inv: dict) -> list[dict]:
    """Skills Codex would put in the list, in Codex's host ordering."""
    visible = [s for s in inv["skills"] if not s["error"] and s["enabled"] and s["implicit"]]
    visible.sort(key=lambda s: (SCOPE_RANK.get(s["scope"], 4), s["name"], s["path"]))
    return visible


def read_body(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
