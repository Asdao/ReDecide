"""Compare saved model metric reports and select the simplest winner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


_COMPATIBILITY_FIELDS = (
    "feature_schema_version",
    "dataset_fingerprint",
    "split_fingerprint",
    "split_schema_version",
)


def _metadata(report: dict[str, Any]) -> dict[str, Any]:
    metadata = report.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    # A few early reports stored these fields at the root.  Reading them here
    # keeps the comparison code compatible while requiring all fields for a
    # multi-report comparison.
    return {field: report[field] for field in _COMPATIBILITY_FIELDS if field in report}


def _check_compatible(reports: list[tuple[Path, dict[str, Any]]]) -> dict[str, Any] | None:
    if len(reports) <= 1:
        return _metadata(reports[0][1]) if reports else None
    metadata = [_metadata(report) for _, report in reports]
    missing = [str(path) for (path, _), values in zip(reports, metadata, strict=True) if any(field not in values for field in _COMPATIBILITY_FIELDS)]
    if missing:
        raise ValueError(
            "cannot compare model reports without matching dataset/schema/split metadata: "
            + ", ".join(missing)
        )
    reference = {field: metadata[0][field] for field in _COMPATIBILITY_FIELDS}
    mismatches = [
        str(path)
        for (path, _), values in zip(reports, metadata, strict=True)
        if any(values[field] != reference[field] for field in _COMPATIBILITY_FIELDS)
    ]
    if mismatches:
        raise ValueError("model reports use different dataset, feature schema, or held-out split: " + ", ".join(mismatches))
    return reference


def _metric(report: dict[str, Any], model_name: str) -> dict[str, Any] | None:
    if "models" in report:
        value = report["models"].get(model_name)
        return value.get("round") if isinstance(value, dict) else None
    if model_name == "lightgbm" and isinstance(report.get("round_metrics"), dict):
        return report["round_metrics"]
    return None


def compare_reports(report_paths: list[Path], *, output_path: Path | None = None) -> dict[str, Any]:
    reports: list[tuple[Path, dict[str, Any]]] = []
    for path in report_paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        reports.append((path, report))
    compatibility = _check_compatible(reports)
    candidates: list[dict[str, Any]] = []
    for path, report in reports:
        if "models" in report:
            for model_name in report["models"]:
                metrics = _metric(report, model_name)
                if metrics is not None:
                    candidates.append(
                        {
                            "name": model_name,
                            "source": str(path),
                            "metrics": metrics,
                            "role": report.get("role", "advisory_baseline"),
                        }
                    )
        else:
            metrics = _metric(report, "lightgbm")
            if metrics is not None:
                candidates.append(
                    {
                        "name": "lightgbm",
                        "source": str(path),
                        "metrics": metrics,
                        "role": "deployed_replay_value_model",
                    }
                )
    if not candidates:
        raise ValueError("no compatible model metrics found")
    candidates.sort(key=lambda item: (float(item["metrics"].get("log_loss", float("inf"))), item["name"]))
    result = {
        "candidates": candidates,
        "selected": candidates[0],
        "selection_rule": "lowest held-out round log loss",
    }
    if compatibility:
        result["metadata"] = compatibility
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/model_comparison.json"))
    args = parser.parse_args()
    result = compare_reports(args.reports, output_path=args.output)
    print(f"[evaluate] selected={result['selected']['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
