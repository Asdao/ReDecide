"""Small user-facing runner for the combined replay-analysis harness.

The core implementation lives in :mod:`Noah.training.analysis_harness`.  This
wrapper intentionally keeps the normal path to one required argument: an
extracted replay JSON or JSONL file.  Model release selection and conservative
probability thresholds use the deployed defaults.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _noah_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_replay_record(path: str | Path, *, record_index: int = 0) -> dict[str, Any]:
    """Load one replay mapping from JSON or JSONL input."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"replay input does not exist: {source}")
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"replay input is empty: {source}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        if not isinstance(payload, (dict, list)):
            raise TypeError("JSON replay input must contain an object or list")
        records = payload if isinstance(payload, list) else [payload]
    if record_index < 0 or record_index >= len(records):
        raise IndexError(f"no replay record at index {record_index}: {source}")
    record = records[record_index]
    if not isinstance(record, dict):
        raise TypeError("selected replay record must be a JSON object")
    return record


def run_replay_test(
    input_path: str | Path,
    *,
    record_index: int = 0,
    release_dir: str | Path | None = None,
    version: str = "v2",
) -> dict[str, Any]:
    """Run the deployed model on one extracted replay record."""

    noah_root = _noah_root()
    workspace_root = noah_root.parent
    model_src = noah_root / "model" / "src"
    if str(model_src) not in sys.path:
        sys.path.insert(0, str(model_src))
    if str(workspace_root) not in sys.path:
        sys.path.insert(0, str(workspace_root))
    from cs2_sim import ModelConfig, ReplayModel

    release = (
        Path(release_dir)
        if release_dir is not None
        else noah_root / "model" / "artifacts" / "releases"
    )
    runtime = ReplayModel.load(
        ModelConfig(releases_dir=release, version=version, allow_fallback=True)
    )
    return runtime.analyse_replay(load_replay_record(input_path, record_index=record_index))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="extracted replay JSON or JSONL")
    parser.add_argument("--record-index", type=int, default=0, help="record to test for JSONL/list input")
    parser.add_argument("--output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args()
    report = run_replay_test(args.input, record_index=args.record_index)
    output = args.output or args.input.with_name(f"{args.input.stem}.analysis.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    print(f"[harness] output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["load_replay_record", "main", "run_replay_test"]
