"""Comparison keys only. Never rewrite the path used to open or render a file."""

from __future__ import annotations

import ntpath
import os
import posixpath
import re
from pathlib import Path


def is_windows_path(value: str) -> bool:
    return bool(re.match(r"^(?:[A-Za-z]:[/\\]|\\\\|//)", value))


def path_key(value: str) -> str:
    value = str(value)
    if re.match(r"^[a-z][a-z0-9+.-]*://", value, re.I):
        return value
    if is_windows_path(value):
        value = value.replace("/", "\\")
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return ntpath.normcase(ntpath.normpath(value)).replace("\\", "/")
    return posixpath.normpath(value)


def local_key(value: str) -> str:
    # Foreign Windows paths are comparable on POSIX without being resolved under cwd.
    if is_windows_path(value) and os.name != "nt":
        return path_key(value)
    try:
        return path_key(str(Path(value).expanduser().resolve()))
    except (OSError, RuntimeError):
        return path_key(value)


def is_within(value: str, parent: str) -> bool:
    child, root = path_key(value), path_key(parent).rstrip("/")
    return child == root or child.startswith(root + "/")
