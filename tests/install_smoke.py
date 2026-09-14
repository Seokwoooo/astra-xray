"""Install the tested checkout through npx in an isolated project and run its CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=str(repo))
    args = parser.parse_args()
    npx = shutil.which("npx.cmd" if os.name == "nt" else "npx")
    if not npx:
        raise RuntimeError("npx is required for the distribution smoke test")
    with tempfile.TemporaryDirectory(prefix="astra-install-") as temp:
        work = Path(temp)
        env = dict(os.environ, DO_NOT_TRACK="1", ASTRA_XRAY_HOME=str(work / "state"), PYTHONUTF8="1")
        command = [npx, "--yes", "skills@1.5.26", "add", args.source, "--agent", "codex", "--yes"]
        subprocess.run(command, cwd=work, env=env, check=True, timeout=120)
        installed = work / ".agents" / "skills" / "astra-xray"
        source = repo / "skills" / "astra-xray"
        expected = {p.relative_to(source) for p in source.rglob("*")
                    if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        actual = {p.relative_to(installed) for p in installed.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        if actual != expected:
            raise RuntimeError(f"installed file set differs: {actual ^ expected}")
        for rel in expected:
            if (source / rel).read_bytes() != (installed / rel).read_bytes():
                raise RuntimeError(f"installed bytes differ: {rel}")
        for name in ("scan", "tune", "backup", "restore"):
            subprocess.run([sys.executable, str(installed / "scripts" / f"{name}.py"), "--help"],
                           cwd=work, env=env, check=True, stdout=subprocess.PIPE, timeout=30)
        result = subprocess.run([sys.executable, str(installed / "scripts" / "scan.py"),
                                 "--codex-home", str(work / "empty-codex"), "--session", "none", "--json"],
                                cwd=work, env=env, check=True, capture_output=True, encoding="utf-8", timeout=30)
        report = json.loads(result.stdout)
        assert report["version"] == "0.3.0"
        assert any(s["name"] == "astra-xray" for s in report["skills"]["installed"])
        print(f"Verified {len(expected)} installed files and all four CLI entrypoints on {sys.platform}.")


if __name__ == "__main__":
    main()
