"""One-command RE:DECIDE backend demo.

Native ``.dem`` input goes through the separate Replay FastAPI first. The CLI
then sends the returned ``replay_id`` to Coaching FastAPI, selects a player,
and verifies that the unlocked full visualization JSON is received afterward.
Normalized JSON remains available as a compatibility fallback.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _configure_imports() -> None:
    root = _repo_root()
    for path in (
        root,
        root / "backend" / "replay_engine" / "model" / "src",
        root / "backend" / "replay_engine" / "extractor" / "src",
    ):
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
    candidates.extend(
        sorted((root / "backend" / "replay_engine" / "backend demo").glob("*.dem"))
    )
    candidates.extend(
        sorted((root / "backend" / "replay_engine" / "backend demo").glob("*.demo"))
    )
    candidates.extend(sorted((root / "data" / "private" / "raw_demos").rglob("*.dem")))
    return candidates[0] if candidates else None


def _fallback_path(explicit: Path | None) -> Path:
    return explicit or (_repo_root() / "data" / "private" / "processed" / "full_replays.jsonl")


def _load_input(demo: Path | None, fallback: Path) -> tuple[dict[str, Any] | None, str, Path]:
    if demo is not None:
        if not demo.is_file():
            raise RuntimeError(f"native DEM input does not exist: {demo}")
        # The Replay API owns native parsing. Returning the path prevents the
        # CLI from parsing the same DEM once locally and once in the API.
        return None, f"DEM: {demo}", demo
    from backend.replay_engine.harness import load_replay_record

    try:
        return load_replay_record(fallback), f"JSON: {fallback}", fallback
    except Exception as exc:  # noqa: BLE001 - CLI converts to a stable exit code
        raise RuntimeError(f"could not load JSON fallback: {exc}") from exc


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


def _is_full_visualization_payload(payload: Any) -> bool:
    """Return true only for the complete split artifact sent to the frontend."""

    return (
        isinstance(payload, Mapping)
        and payload.get("schema_version") == "replay_visualization_v1"
        and isinstance(payload.get("replay_id"), str)
        and isinstance(payload.get("map"), Mapping)
        and isinstance(payload.get("players"), list)
        and isinstance(payload.get("rounds"), list)
        and isinstance(payload.get("events"), list)
        and isinstance(payload.get("ticks"), list)
    )


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
    replay: Mapping[str, Any] | None,
    *,
    source: str,
    player_id: str | None,
    source_path: Path | None = None,
) -> None:
    """Run the split Replay API -> Coaching API flow through public routes."""

    from backend.app.main import create_app
    from backend.replay_api.main import create_app as create_replay_app

    app = create_app()
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("HTTP demo client is missing; run with `uv sync --extra test`") from exc

    is_native_demo = source_path is not None and source_path.suffix.lower() == ".dem"
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://re-decide.local",
        ) as client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_replay_app()),
            base_url="http://replay.local",
        ) as replay_client,
    ):
        health = await client.get("/api/health")
        _raise_for_status(health)

        replay_id: str | None = None
        if is_native_demo:
            assert source_path is not None
            demo_bytes = await asyncio.to_thread(source_path.read_bytes)
            uploaded = await replay_client.post(
                "/api/replay/upload",
                files={"file": (source_path.name, demo_bytes, "application/octet-stream")},
            )
            _raise_for_status(uploaded)
            manifest = uploaded.json()
            replay_id = manifest.get("replay_id")
            if not isinstance(replay_id, str) or not replay_id:
                raise RuntimeError("Replay API did not return a replay_id")
            print(
                f"Replay API received DEM; {len(manifest.get('players', []))} players available.",
                file=sys.stderr,
            )
            prepare_body = {"replay_id": replay_id}
        else:
            if replay is None:
                raise RuntimeError("normalized JSON replay is missing")
            prepare_body = {"replay": dict(replay)}

        prepared = await client.post("/api/analysis/prepare", json=prepare_body)
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

        if is_native_demo and replay_id is not None:
            while True:
                visualization_status = await replay_client.get(f"/api/replay/{replay_id}/status")
                _raise_for_status(visualization_status)
                full_response = await replay_client.get(f"/api/replay/{replay_id}/json")
                if int(full_response.status_code) == 202:
                    await asyncio.sleep(0.1)
                    continue
                _raise_for_status(full_response)
                full_visualization = full_response.json()
                break
            received_full = _is_full_visualization_payload(full_visualization)
            print(f"Full visualization JSON received: {str(received_full).lower()}")
            if not received_full:
                raise RuntimeError("Replay API returned an incomplete visualization payload")

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
    print("Starting RE:DECIDE backend demo...", file=sys.stderr)
    demo = _find_demo(args.demo)
    fallback = _fallback_path(args.json_fallback)
    try:
        replay, source, input_path = _load_input(demo, fallback)
        asyncio.run(
            _run_api(
                replay,
                source=source,
                player_id=args.player_id,
                source_path=input_path,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - command-line boundary
        print(f"backend demo failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
