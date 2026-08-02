"""Convert replay-analysis sidecars into compact JSONL snapshots.

The downloaded ``.analysis.json`` files already contain parsed round and kill
events. This extractor keeps those useful, outcome-linked snapshots without
requiring a native ``.dem`` parser. The output is intentionally a streaming
JSONL file so larger demo collections do not need to fit in memory.

Example::

    $env:PYTHONPATH = "src"
    python -m training.extract_features \
        --input data/full \
        --output data/full/processed/analysis_snapshots.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


def _side(value: Any) -> str | None:
    value = str(value).lower() if value is not None else ""
    return value if value in {"ct", "t"} else None


def _roster_counts(match: dict[str, Any]) -> dict[str, int]:
    counts = {"ct": 0, "t": 0}
    for team in match.get("teams") or []:
        side = _side(team.get("side_start"))
        if side is not None:
            counts[side] += len(team.get("players") or [])
    return {side: count or 5 for side, count in counts.items()}


def _kill_is_real(kill: dict[str, Any]) -> bool:
    attacker = kill.get("attacker_steamid")
    victim = kill.get("victim_steamid")
    return kill.get("weapon") != "world" and attacker != victim


def extract_snapshots(document: dict[str, Any], source: str) -> list[dict[str, Any]]:
    """Extract round-start, kill, bomb-plant, and round-end snapshots."""

    match = document.get("match") or {}
    tick_rate = float(match.get("tick_rate") or 128.0)
    roster = _roster_counts(match)
    kills_by_round: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for kill in document.get("kills") or []:
        if _kill_is_real(kill):
            kills_by_round[int(kill.get("round_num") or 0)].append(kill)

    snapshots: list[dict[str, Any]] = []
    for round_info in document.get("rounds") or []:
        round_num = int(round_info.get("round_num") or 0)
        start_tick = int(round_info.get("start") or 0)
        winner = _side(round_info.get("winner"))
        ct_alive, t_alive = roster["ct"], roster["t"]
        bomb_tick = round_info.get("bomb_plant")
        bomb_tick = int(bomb_tick) if bomb_tick is not None else None
        bomb_site = round_info.get("bomb_site")
        bomb_site = bomb_site if bomb_site not in (None, "not_planted") else None
        events: list[tuple[int, int, str, dict[str, Any] | None]] = [
            (start_tick, 0, "round_start", None)
        ]
        for kill in kills_by_round.get(round_num, []):
            tick = int(kill.get("tick") or start_tick)
            events.append((tick, 1, "kill", kill))
        if bomb_tick is not None:
            events.append((bomb_tick, 2, "bomb_plant", None))
        end_tick = int(round_info.get("end") or round_info.get("official_end") or start_tick)
        events.append((end_tick, 3, "round_end", None))
        events.sort(key=lambda event: (event[0], event[1]))

        kills_seen = 0
        bomb_planted = False
        event_index = 0
        for tick, _, event_type, payload in events:
            if event_type == "kill" and payload is not None:
                victim_side = _side(payload.get("victim_side"))
                if victim_side == "ct" and ct_alive > 0:
                    ct_alive -= 1
                elif victim_side == "t" and t_alive > 0:
                    t_alive -= 1
                kills_seen += 1
            elif event_type == "bomb_plant":
                bomb_planted = True
            elapsed_seconds = max(0.0, (tick - start_tick) / tick_rate)
            snapshot: dict[str, Any] = {
                "schema_version": 1,
                "source": source,
                "demo_file": document.get("demo_file"),
                "map_name": match.get("map_name") or (document.get("header") or {}).get("map_name"),
                "patch_version": match.get("patch_version") or (document.get("header") or {}).get("patch_version"),
                "tick_rate": tick_rate,
                "round_num": round_num,
                "tick": tick,
                "elapsed_seconds": elapsed_seconds,
                "event_type": event_type,
                "ct_alive": ct_alive,
                "t_alive": t_alive,
                "alive_difference": ct_alive - t_alive,
                "kills_seen": kills_seen,
                "bomb_planted": bomb_planted,
                "bomb_site": bomb_site,
                # Keep the outcome explicitly named as a label so it is not
                # accidentally included as an input feature.
                "label_round_winner": winner,
            }
            if event_type == "kill" and payload is not None:
                snapshot["kill"] = {
                    "attacker_side": _side(payload.get("attacker_side")),
                    "victim_side": _side(payload.get("victim_side")),
                    "weapon": payload.get("weapon"),
                    "headshot": bool(payload.get("headshot")),
                    "distance": payload.get("distance"),
                    "through_smoke": bool(payload.get("thrusmoke")),
                }
            event_index += 1
            snapshot["snapshot_id"] = f"{source}:{round_num}:{event_index}"
            snapshots.append(snapshot)
    return snapshots


def extract_directory(input_dir: Path, output_path: Path, limit: int | None = None) -> tuple[int, int]:
    files = sorted(input_dir.rglob("*.analysis.json"))
    if limit is not None:
        files = files[:limit]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    demos, snapshots = 0, 0
    partial = output_path.with_name(f"{output_path.name}.part")
    try:
        with partial.open("w", encoding="utf-8") as output:
            for path in files:
                document = json.loads(path.read_text(encoding="utf-8"))
                relative = path.relative_to(input_dir).as_posix()
                rows = extract_snapshots(document, relative)
                for row in rows:
                    output.write(json.dumps(row, separators=(",", ":")) + "\n")
                demos += 1
                snapshots += len(rows)
                print(
                    f"[extract] {demos}/{len(files)} demos, {snapshots} snapshots",
                    flush=True,
                )
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return demos, snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/full/processed/analysis_snapshots.jsonl"),
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not args.input.exists():
        raise FileNotFoundError(args.input)
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be positive")
    demos, snapshots = extract_directory(args.input, args.output, args.limit)
    print(f"[extract] complete: {demos} demos, {snapshots} snapshots -> {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
