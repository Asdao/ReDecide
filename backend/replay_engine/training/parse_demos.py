"""Parse CS2 ``.dem`` files into compact JSON records for the full trainer.

The primary backend is Awpy/demoparser2. A sidecar fallback is available for
the structured ``.analysis.json`` files already shipped with the sample demos.
The fallback keeps the pipeline usable on machines where native parser DLLs
are blocked, but it does not contain positional tick data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.replay_engine.training.data_paths import DATA_PATHS


EVENTS = [
    "round_freeze_end",
    "round_officially_ended",
    "round_start",
    "round_end",
    "player_death",
    "player_hurt",
    "bomb_planted",
    "bomb_defused",
    "bomb_exploded",
    "weapon_fire",
]
PLAYER_PROPS = [
    "team_name",
    "X",
    "Y",
    "Z",
    "last_place_name",
    "health",
    "armor_value",
    "inventory",
    "has_defuser",
]
WORLD_PROPS = ["game_time", "is_bomb_planted", "which_bomb_zone", "is_freeze_period"]


def _rows(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    return frame.to_dicts()


def parse_demo(path: Path, *, tick_interval: int = 32) -> dict[str, Any]:
    """Parse one binary demo using Awpy and sample player ticks."""

    try:
        import pyarrow  # noqa: F401  # Awpy's native backend requires it.
    except ImportError as exc:
        raise RuntimeError(
            "Awpy requires a working PyArrow installation; native DLL loading is blocked"
        ) from exc
    try:
        from awpy import Demo
    except ImportError as exc:
        raise RuntimeError("install the optional full dependencies with `pip install .[full]`") from exc
    if tick_interval <= 0:
        raise ValueError("tick_interval must be positive")
    demo = Demo(path, verbose=False)
    demo.parse(events=EVENTS, player_props=PLAYER_PROPS, other_props=WORLD_PROPS)
    ticks = demo.ticks
    if tick_interval > 1:
        ticks = ticks.filter((ticks["tick"] % tick_interval) == 0)
    return {
        "schema_version": 1,
        "parser": "awpy",
        "demo_file": path.name,
        "source_path": path.as_posix(),
        "header": demo.header,
        "rounds": _rows(demo.rounds),
        "kills": _rows(demo.kills),
        "damages": _rows(demo.damages),
        "bomb": _rows(demo.bomb),
        "events": {
            name: _rows(frame)
            for name, frame in demo.events.items()
        },
        "ticks": _rows(ticks),
    }


def sidecar_record(path: Path) -> dict[str, Any]:
    """Load an existing analysis sidecar as a parser-compatible fallback."""

    record = json.loads(path.read_text(encoding="utf-8"))
    record["parser"] = "analysis_sidecar"
    record.setdefault("source_path", path.with_suffix(".dem").as_posix())
    return record


def parse_directory(
    input_dir: Path,
    output_path: Path,
    *,
    tick_interval: int = 32,
    sidecar_fallback: bool = True,
) -> tuple[int, int]:
    demos = sorted(input_dir.rglob("*.dem"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parsed, fallback = 0, 0
    partial = output_path.with_name(f"{output_path.name}.part")
    try:
        with partial.open("w", encoding="utf-8") as output:
            for index, demo_path in enumerate(demos, start=1):
                try:
                    record = parse_demo(demo_path, tick_interval=tick_interval)
                except BaseException as exc:
                    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                        raise
                    if not sidecar_fallback:
                        raise
                    sidecar_path = demo_path.with_suffix(".analysis.json")
                    if not sidecar_path.exists():
                        raise RuntimeError(f"could not parse {demo_path}: {exc}") from exc
                    record = sidecar_record(sidecar_path)
                    record["parse_warning"] = str(exc)
                    fallback += 1
                output.write(json.dumps(record, separators=(",", ":")) + "\n")
                parsed += 1
                print(
                    f"[parse] {index}/{len(demos)} demos, parser={record['parser']}",
                    flush=True,
                )
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return parsed, fallback


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_raw_demos)
    parser.add_argument("--output", type=Path, default=DATA_PATHS.private_processed / "full_replays.jsonl")
    parser.add_argument("--tick-interval", type=int, default=32)
    parser.add_argument("--no-sidecar-fallback", action="store_true")
    args = parser.parse_args()
    parsed, fallback = parse_directory(
        args.input,
        args.output,
        tick_interval=args.tick_interval,
        sidecar_fallback=not args.no_sidecar_fallback,
    )
    print(f"[parse] complete: {parsed} demos, {fallback} sidecar fallbacks -> {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
