"""Deployment contract tests for the flattened Vercel backend service."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_flattened_entrypoint_exposes_bundled_model_package() -> None:
    entrypoint = REPOSITORY_ROOT / "backend" / "main.py"
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
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_vercel_services_routing_and_private_binding_contract() -> None:
    config = json.loads((REPOSITORY_ROOT / "vercel.json").read_text(encoding="utf-8"))

    assert config["$schema"] == "https://openapi.vercel.sh/vercel.json"
    assert config["services"]["frontend"] == {
        "root": "frontend/",
        "framework": "nextjs",
    }
    assert config["services"]["backend"] == {
        "root": "backend/",
        "framework": "fastapi",
        "entrypoint": "main:app",
        "functions": {"**/*.py": {"maxDuration": 300}},
        "bindings": [
            {
                "type": "service",
                "service": "frontend",
                "format": "url",
                "env": "REDECIDE_BLOB_SERVICE_URL",
            }
        ],
    }

    routes = [
        (rewrite["source"], rewrite["destination"]["service"])
        for rewrite in config["rewrites"]
    ]
    assert routes == [
        ("/api/blob/upload", "frontend"),
        ("/api/blob/cleanup", "frontend"),
        ("/api/cron/blob-retention", "frontend"),
        ("/api/(.*)", "backend"),
        ("/service-internal/(.*)", "backend"),
        ("/(.*)", "frontend"),
    ]
    assert config["crons"] == [
        {"path": "/api/cron/blob-retention", "schedule": "0 3 * * *"}
    ]
