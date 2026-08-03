"""End-to-end smoke tester for replay-value and movement models.

It accepts a native ``.dem``, parsed JSONL, or the canonical SQLite database.
The report is intentionally small enough to run before every demo/presentation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from itertools import islice
from pathlib import Path
from collections.abc import Iterable, Iterator
from typing import Any

from cs2_sim.core.model import ActionFrequencyModel, ReplayValueEnsemble
from training.full_features import record_to_event_rows, record_to_rows
from training.infer_actions import infer_actions
from training.metrics import binary_probability_metrics
from training.parse_demos import parse_demo
from training.replay_extractor_adapter import iter_extractor_jsonl, parse_extractor_demo
from training.train_action_models import action_state_key
from training.replay_repository import ReplayRepository


def _active_release_root() -> Path:
    """Resolve the active release, with v2/legacy fallbacks for old installs."""

    for releases in (Path("model/artifacts/releases"), Path("models/releases")):
        pointer = releases / "current.json"
        if pointer.exists():
            try:
                payload = json.loads(pointer.read_text(encoding="utf-8"))
                version = payload.get("version") if isinstance(payload, dict) else None
                if isinstance(version, str):
                    candidate = releases / version
                    if candidate.is_dir():
                        return candidate
            except (OSError, json.JSONDecodeError):
                pass
        v2 = releases / "v2"
        if v2.is_dir():
            return v2
    for legacy in (Path("model/artifacts"), Path("models")):
        if legacy.is_dir():
            return legacy
    return Path("model/artifacts")


def _default_database() -> Path | None:
    for candidate in (
        Path("data/full/processed/cs2_replays_v2.sqlite"),
        Path("data/full/processed/cs2_replays.sqlite"),
    ):
        if candidate.exists():
            return candidate
    return None


def _read_jsonl_records(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"record in {path} must be a JSON object")
            yield value


def _rows_from_records(
    records: Iterable[dict[str, Any]],
    *,
    sample_every: int,
    decision_window_seconds: float,
    limit: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    for record in records:
        parsed = record_to_rows(
            record,
            sample_every=sample_every,
            decision_window_seconds=decision_window_seconds,
            include_terminal=False,
        )
        if not parsed:
            parsed = record_to_event_rows(
                record,
                decision_window_seconds=decision_window_seconds,
                include_terminal=False,
            )
        rows.extend(parsed)
        action_rows.extend(infer_actions(record, window_seconds=2.0))
        if limit is not None and len(rows) >= limit:
            break
    if limit is not None:
        action_rows = action_rows[:limit]
    return rows[:limit] if limit is not None else rows, action_rows


def test_models(
    *,
    database_path: Path | None = None,
    input_path: Path | None = None,
    demo_path: Path | None = None,
    extractor_input_path: Path | None = None,
    extractor_demo_path: Path | None = None,
    manifest_path: Path | None = None,
    action_model_path: Path | None = None,
    limit: int = 500,
    sample_every: int = 4,
    decision_window_seconds: float = 5.0,
    mode: str = "smoke",
    allow_fallback: bool = False,
    training_prior: float | None = None,
) -> dict[str, Any]:
    if mode not in {"smoke", "evaluation"}:
        raise ValueError("mode must be 'smoke' or 'evaluation'")
    if limit <= 0:
        raise ValueError("limit must be positive")
    if mode == "evaluation" and database_path is not None:
        raise ValueError("evaluation mode requires a registered held-out input, not the training database")
    selected = sum(
        path is not None
        for path in (database_path, input_path, demo_path, extractor_input_path, extractor_demo_path)
    )
    if selected > 1:
        raise ValueError("choose only one input source")
    release_root = _active_release_root()
    manifest_path = manifest_path or (release_root / "full_replay_value.manifest.json")
    action_model_path = action_model_path or (release_root / "action_frequency.json")
    if not manifest_path.exists() and not allow_fallback:
        raise FileNotFoundError(f"model manifest does not exist: {manifest_path}")
    ensemble = ReplayValueEnsemble.load(manifest_path, allow_fallback=allow_fallback)
    rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    source = "bayesian_fallback"
    if database_path is not None:
        source = str(database_path)
        with ReplayRepository(database_path) as repository:
            rows = list(islice(repository.iter_snapshot_rows(include_terminal=False), limit))
            action_rows = list(islice(repository.iter_actions(), limit))
    else:
        if extractor_demo_path is not None:
            source = str(extractor_demo_path)
            # The extractor already samples at the training interval. Applying
            # ``sample_every`` again would make the effective interval quadratic.
            records = [parse_extractor_demo(extractor_demo_path, tick_interval=32)]
        elif extractor_input_path is not None:
            source = str(extractor_input_path)
            records = iter_extractor_jsonl(extractor_input_path)
        elif demo_path is not None:
            source = str(demo_path)
            records = [parse_demo(demo_path, tick_interval=32)]
        else:
            input_file = input_path or Path("data/full/processed/full_replays.jsonl")
            source = str(input_file)
            records = _read_jsonl_records(input_file)
        rows, action_rows = _rows_from_records(
            records,
            sample_every=sample_every,
            decision_window_seconds=decision_window_seconds,
            limit=limit,
        )
    if not rows:
        raise ValueError("no labelled snapshot rows were available for testing")
    probabilities = []
    for row in rows:
        feature_map = row.get("features")
        if isinstance(feature_map, dict):
            vector = [float(feature_map[name]) for name in ensemble.feature_names]
            prediction = ensemble.predict_features(vector, snapshot=row.get("snapshot"))
        else:
            prediction = ensemble.predict(row["snapshot"])
        probabilities.append(prediction.probability)
    labels = [int(row["label_ct_win"]) for row in rows]
    replay_metrics = binary_probability_metrics(probabilities, labels, baseline_probability=training_prior)
    action_counts = Counter(str(row.get("action") or "unknown") for row in action_rows)
    region_counts = Counter(str(row.get("current_zone") or "unknown") for row in action_rows)
    action_model = ActionFrequencyModel.load(action_model_path) if action_model_path.exists() else None
    action_examples = []
    if action_model is not None:
        for row in action_rows[:10]:
            state_key = action_state_key(row)
            action_examples.append(
                {
                    "state": state_key,
                    "scores": action_model.score_actions(state_key, row.get("legal_actions") or ["hold", "move"]),
                }
            )
    return {
        "source": source,
        "evaluation_mode": mode,
        "model_manifest": str(manifest_path),
        "model_components": {
            "booster": ensemble.has_booster,
            "bayesian_samples": ensemble.bayesian.global_sample_count(),
            "calibrator": ensemble.calibrator is not None,
        },
        "snapshot_rows": len(rows),
        "model_has_booster": ensemble.has_booster,
        "replay_metrics": replay_metrics,
        "action_rows": len(action_rows),
        "action_counts": dict(action_counts),
        "top_regions": region_counts.most_common(10),
        "action_examples": action_examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--input", type=Path, default=None, help="parsed replay JSONL")
    parser.add_argument("--demo", type=Path, default=None, help="native CS2 .dem file")
    parser.add_argument(
        "--extractor-input",
        type=Path,
        default=None,
        help="replacement extractor JSONL (tester-only, no database changes)",
    )
    parser.add_argument(
        "--extractor-demo",
        type=Path,
        default=None,
        help="native .dem parsed through extractor (tester-only)",
    )
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--action-model", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    parser.add_argument("--mode", choices=("smoke", "evaluation"), default="smoke")
    parser.add_argument("--allow-fallback", action="store_true", help="allow an explicit degraded Bayesian fallback")
    parser.add_argument("--training-prior", type=float, default=None, help="CT prior from training data for baseline metrics")
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/replay_model_test.json"))
    args = parser.parse_args()
    database_path = args.database
    if (
        database_path is None
        and args.input is None
        and args.demo is None
        and args.extractor_input is None
        and args.extractor_demo is None
    ):
        database_path = _default_database()
    report = test_models(
        database_path=database_path,
        input_path=args.input,
        demo_path=args.demo,
        extractor_input_path=args.extractor_input,
        extractor_demo_path=args.extractor_demo,
        manifest_path=args.manifest,
        action_model_path=args.action_model,
        limit=args.limit,
        sample_every=args.sample_every,
        decision_window_seconds=args.decision_window_seconds,
        mode=args.mode,
        allow_fallback=args.allow_fallback,
        training_prior=args.training_prior,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["replay_metrics"], sort_keys=True))
    print(f"[test] snapshots={report['snapshot_rows']} actions={report['action_rows']} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
