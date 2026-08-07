"""Deployment contract tests for the flattened Vercel backend service."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_flattened_entrypoint_exposes_bundled_model_package() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    entrypoint = repository_root / "backend" / "main.py"
    script = f"""
import importlib.util

spec = importlib.util.spec_from_file_location("vercel_backend_entrypoint", {str(entrypoint)!r})
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

import cs2_sim
assert cs2_sim.__file__ is not None
"""

    result = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
