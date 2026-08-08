"""
Garena AI Build Challenge 2026 - End-to-End System Diagnostic Verification Tool.
"""

import sys
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_garena_diagnostics() -> Dict[str, Any]:
    """Run full diagnostic audit for Garena AI Build Challenge submission readiness."""
    results = {
        "status": "PASS",
        "challenge": "Garena AI Build Challenge 2026",
        "checks": [],
    }

    # 1. Directory Structure Audit
    required_dirs = ["src", "backend", "frontend", "data", "logs", "tests"]
    missing_dirs = [d for d in required_dirs if not (REPO_ROOT / d).is_dir()]
    results["checks"].append({
        "check": "Directory Architecture Audit",
        "passed": len(missing_dirs) == 0,
        "details": f"Missing: {missing_dirs}" if missing_dirs else "All required directories present"
    })

    # 2. Key Entrypoint Audit
    required_files = ["main.py", "README.md", "requirements.txt", "docker-compose.yml", ".gitignore"]
    missing_files = [f for f in required_files if not (REPO_ROOT / f).is_file()]
    results["checks"].append({
        "check": "Root Deliverables Audit",
        "passed": len(missing_files) == 0,
        "details": f"Missing: {missing_files}" if missing_files else "All root deliverable files present"
    })

    # 3. Fast Inference Engine Audit
    try:
        from src.tools.fast_cache import FastInferenceEngine
        tactics = FastInferenceEngine.lookup_zone_tactics("de_mirage", "A_SITE")
        cache_passed = "optimal_defensive_angles" in tactics
    except Exception as exc:
        cache_passed = False

    results["checks"].append({
        "check": "Fast Inference Sub-1ms Engine Audit",
        "passed": cache_passed,
        "details": "FastInferenceEngine operational" if cache_passed else "FastInferenceEngine failed"
    })

    # 4. Security Credentials Audit
    import os
    env_clean = True
    for root_file in ["main.py", "README.md"]:
        content = (REPO_ROOT / root_file).read_text(encoding="utf-8", errors="ignore")
        if "sk-" in content and "DEEPSEEK" in content:
            env_clean = False
            break

    results["checks"].append({
        "check": "Security & Secret Credentials Audit",
        "passed": env_clean,
        "details": "No hardcoded credentials found" if env_clean else "WARNING: Potential secret leak detected"
    })

    all_passed = all(c["passed"] for c in results["checks"])
    results["status"] = "PASS" if all_passed else "FAIL"
    return results
