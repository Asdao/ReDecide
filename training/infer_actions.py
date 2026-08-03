"""Infer fixed-window movement actions from positional replay ticks."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _side(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return "unknown"


def _identity(row: dict[str, Any], ordinal: int) -> str:
    for key in ("steamid", "steam_id", "player_steamid", "name", "player_name"):
        if row.get(key) not in (None, ""):
            return str(row[key])
    return f"anonymous:{ordinal}"


def _zone(row: dict[str, Any]) -> str:
    named = row.get("last_place_name") or row.get("zone")
    if named not in (None, ""):
        return str(named)
    x = _number(row.get("X") if "X" in row else row.get("x"), float("nan"))
    y = _number(row.get("Y") if "Y" in row else row.get("y"), float("nan"))
    if math.isfinite(x) and math.isfinite(y):
        # Native demos do not always expose last_place_name. A coarse spatial
        # bucket keeps the Markov model useful without pretending it is a
        # named map callout.
        return f"grid:{math.floor(x / 1000.0)}:{math.floor(y / 1000.0)}"
    return "unknown"


def infer_actions(
    record: dict[str, Any],
    *,
    window_seconds: float = 1.0,
    tick_rate: float | None = None,
    movement_threshold: float = 20.0,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Return movement labels with no future-round or terminal-state leakage."""

    if window_seconds <= 0 or movement_threshold < 0:
        raise ValueError("window_seconds must be positive and movement_threshold cannot be negative")
    header = record.get("header") or {}
    rate = tick_rate or _number(header.get("tick_rate"), 128.0)
    if rate <= 0:
        raise ValueError("tick_rate must be positive")
    grouped: dict[tuple[int, str], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for ordinal, row in enumerate(record.get("ticks") or []):
        round_num = int(_number(row.get("round_num"), -1))
        tick = int(_number(row.get("tick"), -1))
        if round_num < 0 or tick < 0:
            continue
        grouped[(round_num, _identity(row, ordinal))].append((tick, row))

    output: list[dict[str, Any]] = []
    window_ticks = max(1, int(round(window_seconds * rate)))
    for (round_num, player_id), series in grouped.items():
        series.sort(key=lambda item: item[0])
        for index, (tick, current) in enumerate(series):
            if _number(current.get("health"), 100.0) <= 0:
                continue
            future = next(
                ((future_tick, row) for future_tick, row in series[index + 1 :] if future_tick >= tick + window_ticks),
                None,
            )
            if future is None:
                continue
            next_tick, next_row = future
            x1 = _number(current.get("X") if "X" in current else current.get("x"))
            y1 = _number(current.get("Y") if "Y" in current else current.get("y"))
            x2 = _number(next_row.get("X") if "X" in next_row else next_row.get("x"))
            y2 = _number(next_row.get("Y") if "Y" in next_row else next_row.get("y"))
            distance = math.hypot(x2 - x1, y2 - y1)
            current_zone = _zone(current)
            next_zone = _zone(next_row)
            action = "move" if distance >= movement_threshold else "hold"
            output.append(
                {
                    "source": record.get("source_path") or record.get("demo_file") or "unknown",
                    "round_num": round_num,
                    "tick": tick,
                    "next_tick": next_tick,
                    "player_id": player_id,
                    "side": _side(current.get("team_name") or current.get("team") or current.get("side")),
                    "current_zone": str(current_zone),
                    "next_zone": str(next_zone),
                    "action": action,
                    "distance": distance,
                    "window_seconds": window_seconds,
                    "horizon_ticks": next_tick - tick,
                    "legal_actions": ["hold", "move"],
                    "outcome": {
                        "zone_changed": str(current_zone) != str(next_zone),
                        "distance": distance,
                        "health_delta": _number(next_row.get("health"), 0.0)
                        - _number(current.get("health"), 0.0),
                    },
                }
            )
            if max_rows is not None and len(output) >= max_rows:
                return output
    return output


def infer_file(input_path: Path, output_path: Path, *, window_seconds: float = 1.0, movement_threshold: float = 20.0) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    partial = output_path.with_name(f"{output_path.name}.part")
    with input_path.open(encoding="utf-8") as source, partial.open("w", encoding="utf-8") as target:
        for line in source:
            if not line.strip():
                continue
            record = json.loads(line)
            for row in infer_actions(
                record,
                window_seconds=window_seconds,
                movement_threshold=movement_threshold,
            ):
                target.write(json.dumps(row, separators=(",", ":")) + "\n")
                count += 1
    partial.replace(output_path)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/full_replays.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/full/processed/player_actions.jsonl"))
    parser.add_argument("--window-seconds", type=float, default=1.0)
    parser.add_argument("--movement-threshold", type=float, default=20.0)
    args = parser.parse_args()
    count = infer_file(
        args.input,
        args.output,
        window_seconds=args.window_seconds,
        movement_threshold=args.movement_threshold,
    )
    print(f"[actions] inferred {count} labels -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
