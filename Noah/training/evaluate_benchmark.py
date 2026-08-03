"""Evaluate a sealed native-demo benchmark without touching training data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean
from typing import Any

from Noah.training.benchmark_dataset import demo_keys, training_demo_keys
from Noah.training.data_paths import DATA_PATHS
from Noah.training.test_replay_models import test_models


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read benchmark manifest {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("type") != "held_out_native_demo_benchmark":
        raise ValueError("benchmark manifest has an unsupported type")
    if payload.get("training_excluded") is not True:
        raise ValueError("benchmark manifest is not marked training-excluded")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("benchmark manifest contains no demo files")
    return payload


def _verify_manifest_overlap(manifest: dict[str, Any], manifest_path: Path) -> None:
    database_value = manifest.get("training_database")
    if not isinstance(database_value, str) or not database_value:
        raise ValueError("benchmark manifest must record training_database")
    database_path = _resolve_reference(database_value, manifest_path)
    if not database_path.exists():
        raise FileNotFoundError(f"training database recorded by benchmark is missing: {database_path}")
    excluded = training_demo_keys(database_path)
    overlap: list[str] = []
    for entry in manifest["files"]:
        if not isinstance(entry, dict):
            raise ValueError("benchmark manifest file entries must be objects")
        keys = demo_keys(entry.get("repo_path"), entry.get("match_id"), entry.get("local_path"))
        if keys & excluded:
            overlap.append(str(entry.get("repo_path") or entry.get("local_path")))
    if overlap:
        raise ValueError("benchmark contains training demos: " + ", ".join(overlap))


def _entry_path(entry: dict[str, Any], manifest_path: Path) -> Path:
    value = entry.get("local_path")
    if not isinstance(value, str) or not value:
        raise ValueError("benchmark file is missing local_path")
    path = _resolve_reference(value, manifest_path)
    allowed_root = DATA_PATHS.private.resolve() if value.startswith("private:") else manifest_path.parent.resolve()
    try:
        path.relative_to(allowed_root)
    except ValueError as exc:
        raise ValueError(f"benchmark demo escapes its storage root: {path}") from exc
    if not path.is_file():
        raise FileNotFoundError(f"benchmark demo does not exist: {path}")
    return path


def _resolve_reference(value: str, manifest_path: Path) -> Path:
    """Resolve portable private references and legacy manifest paths."""

    if value.startswith("private:"):
        relative = Path(value.removeprefix("private:"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe private benchmark reference: {value}")
        return (DATA_PATHS.private / relative).resolve()
    path = Path(value)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def evaluate_benchmark(
    benchmark_manifest: Path,
    *,
    model_manifest: Path | None = None,
    action_model: Path | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Run the replay tester once per sealed demo and return macro metrics."""

    manifest = _load_manifest(benchmark_manifest)
    _verify_manifest_overlap(manifest, benchmark_manifest)
    reports: list[dict[str, Any]] = []
    for entry in manifest["files"]:
        path = _entry_path(entry, benchmark_manifest)
        report = test_models(
            demo_path=path,
            manifest_path=model_manifest,
            action_model_path=action_model,
            limit=limit,
            mode="evaluation",
        )
        reports.append(
            {
                "repo_path": entry.get("repo_path"),
                "map_name": entry.get("map_name"),
                "local_path": str(path),
                "snapshot_rows": report["snapshot_rows"],
                "action_rows": report["action_rows"],
                "replay_metrics": report["replay_metrics"],
                "action_counts": report["action_counts"],
            }
        )
    metric_names = ("accuracy", "balanced_accuracy", "log_loss", "brier", "expected_calibration_error")
    macro_metrics = {
        name: fmean(
            float(item["replay_metrics"][name])
            for item in reports
            if item["replay_metrics"].get(name) is not None
        )
        for name in metric_names
    }
    return {
        "evaluation_mode": "sealed_unseen_demo",
        "benchmark_manifest": str(benchmark_manifest),
        "model_manifest": str(model_manifest) if model_manifest is not None else "active_release",
        "demo_count": len(reports),
        "macro_metrics": macro_metrics,
        "note": "macro-average across unseen demos; this is separate from training and not a counterfactual action-quality score",
        "demos": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-manifest", type=Path, default=DATA_PATHS.public_benchmark_manifest)
    parser.add_argument("--model-manifest", type=Path, default=None)
    parser.add_argument("--action-model", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--output", type=Path, default=DATA_PATHS.public_benchmark_evaluation)
    args = parser.parse_args()
    report = evaluate_benchmark(
        args.benchmark_manifest,
        model_manifest=args.model_manifest,
        action_model=args.action_model,
        limit=args.limit,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["macro_metrics"], sort_keys=True))
    print(f"[benchmark] demos={report['demo_count']} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
