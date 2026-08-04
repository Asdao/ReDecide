"""Audit parsed replay JSONL and optionally write a versioned cleaned copy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.replay_engine.training.data_paths import DATA_PATHS

from backend.replay_engine.training.replay_cleaning import CleaningOptions, clean_records


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def audit_file(
    input_path: Path,
    report_path: Path,
    *,
    clean_output: Path | None = None,
    options: CleaningOptions | None = None,
) -> dict[str, Any]:
    records = _read_records(input_path)
    cleaned, report = clean_records(records, options=options)
    report["input"] = str(input_path)
    report["clean_output"] = str(clean_output) if clean_output else None
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if clean_output is not None:
        clean_output.parent.mkdir(parents=True, exist_ok=True)
        partial = clean_output.with_name(f"{clean_output.name}.part")
        with partial.open("w", encoding="utf-8") as target:
            for record in cleaned:
                target.write(json.dumps(record, separators=(",", ":")) + "\n")
        partial.replace(clean_output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "full_replays.jsonl")
    parser.add_argument("--report", type=Path, default=DATA_PATHS.private_processed / "replay_audit.json")
    parser.add_argument("--clean-output", type=Path, default=None)
    parser.add_argument("--max-round-seconds", type=float, default=180.0)
    parser.add_argument("--coordinate-limit", type=float, default=20_000.0)
    args = parser.parse_args()
    report = audit_file(
        args.input,
        args.report,
        clean_output=args.clean_output,
        options=CleaningOptions(
            max_round_seconds=args.max_round_seconds,
            coordinate_limit=args.coordinate_limit,
        ),
    )
    print(
        f"[audit] replays={report['replay_count']} errors={report['error_count']} "
        f"warnings={report['warning_count']} report={args.report}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
