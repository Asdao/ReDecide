"""One-command RE:DECIDE backend demo.

The runner tries a native ``.dem`` first, falls back to normalized JSON when
extraction is unavailable, runs the FastAPI replay pipeline, then sends the
selected decision to the server-side Pi coach adapter.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _configure_imports() -> None:
    root = _repo_root()
    for path in (root, root / "Noah" / "model" / "src", root / "Noah" / "extractor" / "src"):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RE:DECIDE backend pipeline.")
    parser.add_argument(
        "--demo",
        type=Path,
        help="native CS2 .dem input; if it cannot be parsed, JSON fallback is used",
    )
    parser.add_argument(
        "--json",
        dest="json_fallback",
        type=Path,
        help="normalized JSON fallback (defaults to the local replay JSONL)",
    )
    parser.add_argument("--player-id", help="select a player without prompting")
    return parser


def _find_demo(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    root = _repo_root()
    candidates = sorted((root / "data" / "samples").glob("*.dem"))
    candidates.extend(sorted((root / "data" / "samples").glob("*.demo")))
    candidates.extend(sorted((root / "Noah" / "backend demo").glob("*.dem")))
    candidates.extend(sorted((root / "Noah" / "backend demo").glob("*.demo")))
    candidates.extend(sorted((root / "data" / "private" / "raw_demos").rglob("*.dem")))
    return candidates[0] if candidates else None


def _fallback_path(explicit: Path | None) -> Path:
    return explicit or (_repo_root() / "data" / "private" / "processed" / "full_replays.jsonl")


def _load_input(demo: Path | None, fallback: Path) -> tuple[dict[str, Any], str, Path]:
    from Noah.harness import load_replay_record

    if demo is not None:
        try:
            return load_replay_record(demo), f"DEM: {demo}", demo
        except Exception as exc:  # noqa: BLE001 - fallback boundary is intentional
            print(f"DEM failed; JSON fallback: {exc}", file=sys.stderr)
    try:
        return load_replay_record(fallback), f"JSON: {fallback}", fallback
    except Exception as exc:  # noqa: BLE001 - CLI converts to a stable exit code
        raise RuntimeError(f"could not load DEM or JSON fallback: {exc}") from exc


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_probability(event: Mapping[str, Any], timeline: Sequence[Mapping[str, Any]]) -> tuple[float | None, float | None]:
    tick = _number(event.get("tick"))
    round_number = _number(event.get("round_number"))
    if tick is None or not timeline:
        return None, None
    same_round = [row for row in timeline if _number(row.get("round_number")) == round_number]
    rows = same_round or list(timeline)
    before = [row for row in rows if (_number(row.get("tick")) or 0) <= tick]
    row = (before or rows)[-1]
    return _number(row.get("ct_probability")), _number(row.get("t_probability"))


def _format_probability(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _raise_for_status(response: Any) -> None:
    """Raise an actionable API error while preserving FastAPI's safe detail."""

    if int(response.status_code) < 400:
        return
    try:
        detail = response.json().get("detail")
    except (AttributeError, TypeError, ValueError):
        detail = None
    if isinstance(detail, str) and detail.strip():
        raise RuntimeError(f"{detail.strip()} (HTTP {response.status_code})")
    response.raise_for_status()


def _display(result: Mapping[str, Any], *, source: str) -> None:
    header = result.get("map_name") or "unknown map"
    timeline = result.get("win_estimator", {}).get("timeline", [])
    if not isinstance(timeline, list):
        timeline = []
    players = {
        str(player.get("player_id")): str(player.get("display_name") or player.get("player_id"))
        for player in result.get("players", [])
        if isinstance(player, Mapping)
    }
    tick_rate = _number(result.get("tick_rate")) or 64.0
    selected_decision = result.get("selected_decision")
    selected_tick = _number(selected_decision.get("contact_tick")) if isinstance(selected_decision, Mapping) else None
    coach = result.get("coach_analysis")
    coach_text = coach.get("what_could_be_done_better") if isinstance(coach, Mapping) else None
    print(f"backend demo input: {header} | {source}", file=sys.stderr)
    for event in result.get("key_events", []):
        if not isinstance(event, Mapping):
            continue
        tick = _number(event.get("tick")) or 0.0
        time_seconds = tick / tick_rate
        participants = [players.get(str(item), str(item)) for item in event.get("participant_ids", [])]
        label = str(event.get("key_event_type") or event.get("event_type") or "event").upper()
        ct_probability, t_probability = _event_probability(event, timeline)
        subject = " -> ".join(participants)
        suffix = f"  {subject}" if subject else ""
        print(f"{time_seconds:07.2f}  {label:<20}{suffix:<30}CT {_format_probability(ct_probability)} | T {_format_probability(t_probability)}")
        if event.get("is_key_event") and coach_text and (selected_tick is None or tick == selected_tick):
            print(f"           Better: {coach_text}")


def _choose_player(players: list[Mapping[str, Any]], requested_id: str | None) -> Mapping[str, Any]:
    eligible = [item for item in players if item.get("decision_ids")]
    if not eligible:
        raise RuntimeError("backend pipeline produced no eligible player decision")
    if requested_id:
        selected = next((item for item in eligible if str(item.get("player_id")) == requested_id), None)
        if selected is None:
            raise RuntimeError(f"player {requested_id!r} has no eligible decision")
        return selected
    print("\nPlayers available:")
    for index, item in enumerate(eligible, start=1):
        print(f"  {index}. {item.get('display_name') or item.get('player_id')} ({item.get('player_id')})")
    answer = input("Select player [1]: ").strip() or "1"
    try:
        selected = eligible[int(answer) - 1]
    except (ValueError, IndexError) as exc:
        raise RuntimeError("invalid player selection") from exc
    return selected


async def _run_api(
    replay: Mapping[str, Any], *, source: str, player_id: str | None
) -> None:
    """Run the complete flow through FastAPI's public routes."""

    from backend.app.main import create_app

    app = create_app()
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("HTTP demo client is missing; run with `uv sync --extra test`") from exc

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://re-decide.local",
    ) as client:
        health = await client.get("/api/health")
        _raise_for_status(health)
        prepared = await client.post("/api/analysis/prepare", json={"replay": dict(replay)})
        _raise_for_status(prepared)
        analysis_id = prepared.json()["analysis_id"]
        print("Preparing replay through FastAPI; press Ctrl+C to stop.", file=sys.stderr)
        while True:
            metadata_response = await client.get(f"/api/analysis/{analysis_id}")
            _raise_for_status(metadata_response)
            metadata = metadata_response.json()
            if metadata.get("status") == "failed":
                raise RuntimeError("backend replay preparation failed")
            if metadata.get("players_available"):
                break
            await asyncio.sleep(0.1)
        players_response = await client.get(f"/api/analysis/{analysis_id}/players")
        _raise_for_status(players_response)
        players = players_response.json().get("players", [])
        selected = _choose_player(players, player_id)
        run = await client.post(
            f"/api/analysis/{analysis_id}/run",
            json={"player_id": selected["player_id"]},
        )
        _raise_for_status(run)
        events = await client.get(f"/api/analysis/{analysis_id}/events")
        _raise_for_status(events)
        result_response = await client.get(f"/api/analysis/{analysis_id}/result")
        _raise_for_status(result_response)
        result = result_response.json()
        outcome = result.get("replay_outcome")
        if isinstance(outcome, Mapping) and outcome.get("eventual_winner"):
            score = outcome.get("round_score")
            score_text = ""
            if isinstance(score, Mapping):
                score_text = f" ({score.get('CT', 0)}-{score.get('T', 0)})"
            print(f"Eventual winner: {outcome['eventual_winner']}{score_text}")
        _display(result, source=source)


def main(argv: Sequence[str] | None = None) -> int:
    _configure_imports()
    args = _parser().parse_args(argv)
    demo = _find_demo(args.demo)
    fallback = _fallback_path(args.json_fallback)
    try:
        replay, source, _ = _load_input(demo, fallback)
        asyncio.run(_run_api(replay, source=source, player_id=args.player_id))
        return 0
    except Exception as exc:  # noqa: BLE001 - command-line boundary
        print(f"backend demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
