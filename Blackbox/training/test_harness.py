"""Small user-facing runner for the combined replay-analysis harness.

The orchestration facade lives in :mod:`Blackbox.training.analysis_harness`, with
state, candidate, and report helpers split into adjacent modules. This wrapper
intentionally keeps the normal path to one required argument: an
extracted replay JSON/JSONL file or native ``.dem``. Native demos are parsed
through the replacement extractor in memory; no database or model retraining
is performed. Model release selection and conservative probability thresholds
use the deployed defaults. Use ``--all-moments`` when you need every detected
kill/death/bomb moment instead of the default cap.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Keep the documented direct-script invocation usable from the repository root.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from Blackbox.harness import analyze_replay, load_replay_record


def run_replay_test(
    input_path: str | Path,
    *,
    record_index: int = 0,
    release_dir: str | Path | None = None,
    version: str | None = None,
    candidate_model_path: str | Path | None = None,
    moment_threshold: float = 0.08,
    max_moments: int | None = 25,
    sample_every: int = 8,
) -> dict[str, Any]:
    """Compatibility wrapper for the public :func:`Blackbox.analyze_replay`."""

    return analyze_replay(
        input_path,
        record_index=record_index,
        release_dir=release_dir,
        version=version,
        candidate_model_path=candidate_model_path,
        moment_threshold=moment_threshold,
        max_moments=max_moments,
        sample_every=sample_every,
    )


def _format_probability(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def format_kill_analysis(report: dict[str, Any]) -> list[str]:
    """Format one readable line per kill from a combined analysis report."""

    rows = report.get("kill_analysis") or []
    if not isinstance(rows, list) or not rows:
        return ["Kill analysis: no kill moments were detected."]
    lines = ["Kill analysis (probabilities are model estimates):"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        supported = (
            "supported"
            if row.get("recommendation_supported")
            else str(row.get("recommendation_support_reason") or "unsupported")
        )
        weapon = row.get("weapon") or "unknown weapon"
        observed = row.get("observed_action") or "unknown"
        recommended = row.get("recommended_action") or "unavailable"
        least_risk = row.get("least_death_risk_action") or "unavailable"
        label = row.get("probability_decision_class") or "unlabeled"
        support_level = row.get("recommendation_support_level") or "unknown"
        lines.append(
            f"  Kill {row.get('kill_number', '?')}: "
            f"R{row.get('round_num', '?')} tick {row.get('tick', '?')} "
            f"{row.get('attacker_id') or '?'} -> {row.get('victim_id') or '?'} ({weapon}); "
            f"observed={observed}; best_estimate={recommended}; "
            f"least_death_risk={least_risk} "
            f"(P({'death proxy' if row.get('least_death_is_proxy', True) else 'death'})="
            f"{_format_probability(row.get('least_death_probability'))}, "
            f"upper={_format_probability(row.get('least_death_risk_upper_bound'))}, "
            f"support={row.get('least_death_risk_support', 0)}, "
            f"supported={'yes' if row.get('least_death_risk_supported') else 'no'}, "
            f"status={row.get('least_death_risk_status') or 'unknown'}, "
            f"source={row.get('least_death_risk_source') or 'unknown'}); "
            f"P(round win)={_format_probability(row.get('round_win_probability'))}; "
            f"P(round-loss proxy)={_format_probability(row.get('round_loss_probability_proxy'))}; "
            f"P(improvement)={_format_probability(row.get('probability_of_improvement'))}; "
            f"label={label}; support={row.get('recommendation_sample_count', 0)} "
            f"({support_level}, {supported}) probability={label}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="native .dem, extracted replay JSON, or JSONL")
    parser.add_argument("--record-index", type=int, default=0, help="record to test for JSONL/list input")
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=None,
        help="release bundle root (defaults to Blackbox/model/artifacts/releases)",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="release version directory (defaults to the active current.json pointer)",
    )
    parser.add_argument(
        "--candidate-model",
        type=Path,
        default=None,
        help="optional candidate_action_value.txt or small_statistical.json override",
    )
    parser.add_argument("--moment-threshold", type=float, default=0.08)
    parser.add_argument("--max-moments", type=int, default=25)
    parser.add_argument(
        "--all-moments",
        action="store_true",
        help="analyze every detected kill/death/bomb moment instead of the default cap",
    )
    parser.add_argument(
        "--show-moments",
        "--print-moments",
        action="store_true",
        help="print one detailed line per kill after the summary",
    )
    parser.add_argument("--sample-every", type=int, default=8)
    parser.add_argument("--output", type=Path, default=None, help="optional JSON report path")
    args = parser.parse_args()
    report = analyze_replay(
        args.input,
        record_index=args.record_index,
        release_dir=args.release_dir,
        version=args.version,
        candidate_model_path=args.candidate_model,
        moment_threshold=args.moment_threshold,
        max_moments=None if args.all_moments else args.max_moments,
        sample_every=args.sample_every,
    )
    output = args.output or args.input.with_name(f"{args.input.stem}.analysis.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    if args.all_moments or args.show_moments:
        print("\n".join(format_kill_analysis(report)))
    print(f"[harness] output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["format_kill_analysis", "load_replay_record", "main", "run_replay_test"]
