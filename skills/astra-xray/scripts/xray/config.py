"""Read-only access to Codex home, config.toml, the models cache and the installed CLI version."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import constants as C

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - exercised only on old Pythons
    _toml = None


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    return Path(env).expanduser() if env else Path.home() / ".codex"


def _parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1].replace('\\"', '"')
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    if re.fullmatch(r"-?\d+", raw.replace("_", "")):
        return int(raw.replace("_", ""))
    if raw.startswith("[") and raw.endswith("]"):
        return [_parse_value(item) for item in re.findall(r'"[^"]*"|\'[^\']*\'|[^,\s]+', raw[1:-1])]
    return raw


def _split_key(header: str) -> list[str]:
    return [part.strip('"') for part in re.findall(r'"[^"]*"|[^.]+', header)]


def _fallback_toml(text: str) -> dict:
    """Enough TOML for the keys astra-xray reads when tomllib is unavailable."""
    root: dict = {}
    current = root
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        array = re.fullmatch(r"\[\[(.+)\]\]", line)
        table = re.fullmatch(r"\[(.+)\]", line)
        if array or table:
            keys = _split_key((array or table).group(1))
            node = root
            for key in keys[:-1]:
                node = node.setdefault(key, {})
            if array:
                current = {}
                node.setdefault(keys[-1], []).append(current)
            else:
                current = node.setdefault(keys[-1], {})
            continue
        key, sep, value = line.partition("=")
        if sep:
            current[key.strip().strip('"')] = _parse_value(re.sub(r"\s+#.*$", "", value))
    return root


def load_config(home: Path) -> dict:
    path = home / "config.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        return _toml.loads(text) if _toml else _fallback_toml(text)
    except Exception as exc:  # malformed config should not stop the scan
        return {"_error": f"config.toml could not be parsed: {exc}"}


def get(cfg: dict, dotted: str, default=None):
    node = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def version_tuple(version: str | None) -> tuple:
    if not version:
        return ()
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    return tuple(int(x) for x in match.groups()) if match else ()


def codex_cli_version() -> str | None:
    exe = shutil.which("codex")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\d+\.\d+\.\d+[\w.\-]*", out.stdout + out.stderr)
    return match.group(0) if match else None


def model_context_window(cfg: dict, home: Path, model: str | None) -> tuple[int | None, str]:
    """Context window Codex uses for the skills budget, and where the number came from."""
    configured = get(cfg, "model_context_window")
    if isinstance(configured, int) and configured > 0:
        return configured, "config.toml model_context_window"
    if model:
        try:
            cache = json.loads((home / "models_cache.json").read_text(encoding="utf-8"))
            models = cache.get("models", cache) if isinstance(cache, dict) else cache
            for entry in models or []:
                if isinstance(entry, dict) and entry.get("slug") == model:
                    window = entry.get("context_window") or entry.get("max_context_window")
                    if window:
                        return int(window), "models_cache.json"
        except (OSError, ValueError):
            pass
        if model in C.KNOWN_CONTEXT_WINDOWS:
            return C.KNOWN_CONTEXT_WINDOWS[model], f"Codex {C.CODEX_PINNED_VERSION} models.json"
    return None, "unknown (Codex falls back to an 8,000-character budget)"


def project_trust(cfg: dict, path: Path) -> str | None:
    projects = get(cfg, "projects", {}) or {}
    best, best_len = None, -1
    target = str(path)
    for key, value in projects.items():
        if not isinstance(value, dict):
            continue
        key_norm = key.rstrip("/")
        if (target == key_norm or target.startswith(key_norm + "/")) and len(key_norm) > best_len:
            best, best_len = value.get("trust_level"), len(key_norm)
    return best
