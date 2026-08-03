"""Optional Awpy adapter and JSONL ingestion helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


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
PLAYER_PROPS = ["team_name", "X", "Y", "Z", "last_place_name", "health", "armor_value", "inventory", "has_defuser"]
WORLD_PROPS = ["game_time", "is_bomb_planted", "which_bomb_zone", "is_freeze_period"]


def parse_demo(path: Path, *, tick_interval: int = 32) -> dict[str, Any]:
    """Parse one native demo with Awpy; import it only when this path is used."""

    if tick_interval <= 0:
        raise ValueError("tick_interval must be positive")
    try:
        from awpy import Demo
    except ImportError as exc:
        raise RuntimeError("install the optional parser with `pip install -e replay-extractor[full]`") from exc
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
        "events": {name: _rows(frame) for name, frame in demo.events.items()},
        "ticks": _rows(ticks),
    }


def load_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number} of {path}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"record on line {line_number} of {path} must be an object")
            yield value


def parse_directory(
    input_dir: Path,
    output_path: Path,
    *,
    tick_interval: int = 32,
    sidecar_fallback: bool = True,
) -> tuple[int, int]:
    demos = sorted(input_dir.rglob("*.dem"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.part")
    count = 0
    fallback_count = 0
    try:
        with partial.open("w", encoding="utf-8") as output:
            for path in demos:
                try:
                    record = parse_demo(path, tick_interval=tick_interval)
                except Exception as exc:
                    sidecar = path.with_suffix(".analysis.json")
                    if not sidecar_fallback or not sidecar.exists():
                        raise RuntimeError(f"could not parse {path}: {exc}") from exc
                    record = json.loads(sidecar.read_text(encoding="utf-8"))
                    record["parser"] = "analysis_sidecar"
                    record.setdefault("source_path", path.as_posix())
                    record["parse_warning"] = str(exc)
                    fallback_count += 1
                output.write(json.dumps(record, separators=(",", ":")) + "\n")
                count += 1
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return count, fallback_count


def _rows(frame: Any) -> list[dict[str, Any]]:
    return [] if frame is None else frame.to_dicts()
