"""AGENTS.md discovery and byte budget, following codex-rs/core/src/agents_md.rs."""

from __future__ import annotations

import os
from pathlib import Path

from . import constants as C
from .config import get, project_trust


def _file_info(path: Path) -> dict:
    info = {"path": str(path), "bytes": 0, "empty": True, "symlink_to": None}
    if path.is_symlink():
        info["symlink_to"] = os.readlink(path)
    try:
        data = path.read_bytes()
    except OSError:
        info["unreadable"] = True
        return info
    info["bytes"] = len(data)
    info["empty"] = not data.decode("utf-8", errors="replace").strip()
    return info


def find_project_root(cwd: Path, markers: list[str]) -> Path | None:
    if not markers:
        return None
    for directory in [cwd, *cwd.parents]:
        if any((directory / marker).exists() for marker in markers):
            return directory
    return None


def global_instructions(home: Path) -> dict:
    """Codex home: AGENTS.override.md, then AGENTS.md; the first non-empty file wins."""
    candidates = []
    used = None
    for name in (C.AGENTS_OVERRIDE_FILENAME, C.AGENTS_FILENAME):
        path = home / name
        if not path.is_file():
            continue
        info = _file_info(path)
        if used is None and not info["empty"]:
            info["status"] = "loaded"
            used = info
        else:
            info["status"] = "empty" if info["empty"] else "shadowed"
        candidates.append(info)
    return {"files": candidates, "loaded": used["path"] if used else None, "bytes": used["bytes"] if used else 0}


def project_chain(cwd: Path, cfg: dict) -> dict:
    markers = get(cfg, "project_root_markers", C.DEFAULT_PROJECT_ROOT_MARKERS)
    if not isinstance(markers, list):
        markers = C.DEFAULT_PROJECT_ROOT_MARKERS
    fallbacks = [n for n in get(cfg, "project_doc_fallback_filenames", []) or [] if isinstance(n, str) and n]
    max_bytes = get(cfg, "project_doc_max_bytes", C.DEFAULT_PROJECT_DOC_MAX_BYTES)
    if not isinstance(max_bytes, int) or max_bytes < 0:
        max_bytes = C.DEFAULT_PROJECT_DOC_MAX_BYTES

    root = find_project_root(cwd, markers)
    if root is None:
        directories = [cwd]
    else:
        directories = [cwd]
        cursor = cwd
        while cursor != root and cursor.parent != cursor:
            cursor = cursor.parent
            directories.append(cursor)
        directories.reverse()

    names = [C.AGENTS_OVERRIDE_FILENAME, C.AGENTS_FILENAME]
    names += [n for n in fallbacks if n not in names]

    trust = project_trust(cfg, root or cwd)
    untrusted = trust == "untrusted"
    remaining = max_bytes
    files = []
    for directory in directories:
        present = [directory / n for n in names if (directory / n).is_file()]
        if not present:
            continue
        chosen, others = present[0], present[1:]
        info = _file_info(chosen)
        info["dir"] = str(directory)
        info["shadows"] = [_file_info(p) for p in others]
        if untrusted:
            info["status"], info["loaded_bytes"] = "ignored_untrusted_project", 0
        elif remaining == 0:
            info["status"], info["loaded_bytes"] = "dropped_budget_exhausted", 0
        else:
            loaded = min(info["bytes"], remaining)
            try:
                text = chosen.read_bytes()[:loaded].decode("utf-8", errors="replace")
            except OSError:
                text = ""
            if not text.strip():
                info["status"], info["loaded_bytes"] = "empty", 0
            else:
                info["status"] = "truncated" if loaded < info["bytes"] else "loaded"
                info["loaded_bytes"] = loaded
                remaining -= loaded
        files.append(info)

    return {
        "cwd": str(cwd),
        "project_root": str(root) if root else None,
        "trust_level": trust,
        "candidate_names": names,
        "max_bytes": max_bytes,
        "used_bytes": max_bytes - remaining if not untrusted else 0,
        "files": files,
    }


def instruction_files(home: Path, chain: dict, global_info: dict) -> list[Path]:
    """Every instruction file Codex reads or skips, for linting and backups."""
    paths = [Path(f["path"]) for f in global_info["files"]]
    for f in chain["files"]:
        paths.append(Path(f["path"]))
        paths.extend(Path(s["path"]) for s in f["shadows"])
    return paths
