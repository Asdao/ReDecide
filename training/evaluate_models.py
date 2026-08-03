"""Compare saved model metric reports and select the simplest winner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _metric(report: dict[str, Any], model_name: str) -> dict[str, Any] | None:
    if "models" in report:
        value = report["models"].get(model_name)
        return value.get("round") if isinstance(value, dict) else None
    if model_name == "lightgbm" and isinstance(report.get("round_metrics"), dict):
        return report["round_metrics"]
    return None


def compare_reports(report_paths: list[Path], *, output_path: Path | None = None) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for path in report_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if "models" in report:
            for model_name in report["models"]:
                metrics = _metric(report, model_name)
                if metrics is not None:
                    candidates.append({"name": model_name, "source": str(path), "metrics": metrics})
        else:
            metrics = _metric(report, "lightgbm")
            if metrics is not None:
                candidates.append({"name": "lightgbm", "source": str(path), "metrics": metrics})
    if not candidates:
        raise ValueError("no compatible model metrics found")
    candidates.sort(key=lambda item: (float(item["metrics"].get("log_loss", float("inf"))), item["name"]))
    result = {
        "candidates": candidates,
        "selected": candidates[0],
        "selection_rule": "lowest held-out round log loss",
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("models/model_comparison.json"))
    args = parser.parse_args()
    result = compare_reports(args.reports, output_path=args.output)
    print(f"[evaluate] selected={result['selected']['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
