"""Zip backups taken before astra-xray edits anything, and the data restore needs.

A backup holds the original bytes of every file in the change set, a manifest with
hashes, modes and symlink targets, and the list of files that did not exist yet.
Backups live outside the repository so Codex never reads them as skills or AGENTS.md.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import __version__


def state_dir() -> Path:
    env = os.environ.get("ASTRA_XRAY_HOME")
    return Path(env).expanduser() if env else Path.home() / ".astra-xray"


def private_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.replace(tmp, path)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str | None:
    try:
        return sha256_bytes(path.read_bytes())
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def snapshot(path: Path) -> dict:
    info = {"path": str(path), "existed": False, "symlink_to": None}
    if path.is_symlink():
        info["symlink_to"] = os.readlink(path)
    if path.is_file():
        data = path.read_bytes()
        info.update(existed=True, sha256=sha256_bytes(data), size=len(data),
                    mode=path.stat().st_mode & 0o777, resolved=str(path.resolve()))
    return info


def create(changes: list[tuple[str, str]], label: str = "apply", cwd: str | None = None) -> dict:
    """changes: (path, action) with action in modify, create, delete, surface.

    Raises RuntimeError if the archive does not verify; nothing is left behind in that case.
    """
    seen, files = set(), []
    for raw, action in changes:
        path = Path(raw).expanduser().absolute()
        if str(path) in seen:
            continue
        seen.add(str(path))
        if path.exists() and not path.is_file():
            raise RuntimeError(f"not a regular file: {path}")
        info = snapshot(path)
        info["action"] = action
        if info["existed"]:
            info["member"] = f"files/{len(files):05d}"
        elif action not in ("create",):
            info["action"] = "create" if action == "modify" else action
        files.append(info)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_label = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-") or "backup"
    target = state_dir() / "backups" / f"{stamp}-{safe_label}.zip"
    counter = 1
    while target.exists():
        counter += 1
        target = target.with_name(f"{stamp}-{safe_label}-{counter}.zip")
    manifest = {
        "tool": "astra-xray",
        "version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "label": label,
        "host": socket.gethostname(),
        "cwd": cwd or os.getcwd(),
        "files": files,
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(target.parent, 0o700)
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as raw_handle, zipfile.ZipFile(raw_handle, "w", zipfile.ZIP_DEFLATED) as archive:
            for info in files:
                if info.get("member"):
                    data = Path(info["path"]).read_bytes()
                    if sha256_bytes(data) != info["sha256"]:
                        raise RuntimeError(f"file changed while backing up: {info['path']}")
                    archive.writestr(info["member"], data)
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        verify(target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {
        "backup": str(target),
        "files_saved": sum(1 for f in files if f.get("member")),
        "files_to_create": sum(1 for f in files if not f["existed"]),
        "verified": True,
    }


def load(backup: Path) -> tuple[dict, dict | None]:
    with zipfile.ZipFile(backup) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        after_names = sorted(n for n in archive.namelist() if n.startswith("after-") and n.endswith(".json"))
        after = json.loads(archive.read(after_names[-1])) if after_names else None
    return manifest, after


def read_member(backup: Path, member: str) -> bytes:
    with zipfile.ZipFile(backup) as archive:
        return archive.read(member)


def verify(backup: Path) -> None:
    manifest, _ = load(backup)
    with zipfile.ZipFile(backup) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"corrupt member in backup: {bad}")
        for info in manifest["files"]:
            if info.get("member") and sha256_bytes(archive.read(info["member"])) != info["sha256"]:
                raise RuntimeError(f"hash mismatch in backup for {info['path']}")


def seal(backup: Path) -> dict:
    """Record file hashes right after edits, so restore can spot later hand edits."""
    manifest, _ = load(backup)
    state = {info["path"]: sha256_path(Path(info["path"])) for info in manifest["files"]}
    record = {"sealed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": state}
    name = f"after-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
    with zipfile.ZipFile(backup, "a") as archive:
        archive.writestr(name, json.dumps(record, indent=2))
    changed = sum(1 for info in manifest["files"] if state[info["path"]] != info.get("sha256"))
    return {"backup": str(backup), "sealed": True, "files_changed_since_backup": changed}


def list_backups() -> list[dict]:
    folder = state_dir() / "backups"
    rows = []
    for path in sorted(folder.glob("*.zip"), reverse=True) if folder.is_dir() else []:
        try:
            manifest, after = load(path)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            rows.append({"backup": str(path), "error": "unreadable"})
            continue
        rows.append({
            "backup": str(path),
            "created_at": manifest["created_at"],
            "label": manifest["label"],
            "files": len(manifest["files"]),
            "sealed": after is not None,
        })
    return rows
