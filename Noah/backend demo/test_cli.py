"""Provider-free tests for the FastAPI-backed backend demo CLI."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest


CLI_PATH = Path(__file__).with_name("cli.py")
SPEC = importlib.util.spec_from_file_location("re_decide_backend_demo_cli", CLI_PATH)
assert SPEC is not None and SPEC.loader is not None
CLI = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CLI
SPEC.loader.exec_module(CLI)


def test_choose_player_defaults_to_first_eligible_and_honors_requested_id() -> None:
    players = [
        {"player_id": "no-decision", "display_name": "No Contact", "decision_ids": []},
        {"player_id": "t1", "display_name": "T One", "decision_ids": ["decision-1"]},
        {"player_id": "ct1", "display_name": "CT One", "decision_ids": ["decision-2"]},
    ]

    with patch("builtins.input", return_value=""):
        assert CLI._choose_player(players, None)["player_id"] == "t1"
    assert CLI._choose_player(players, "ct1")["display_name"] == "CT One"


def test_choose_player_rejects_missing_eligible_selection() -> None:
    with pytest.raises(RuntimeError, match="no eligible player decision"):
        CLI._choose_player([{"player_id": "t1", "decision_ids": []}], None)
    with pytest.raises(RuntimeError, match="has no eligible decision"):
        CLI._choose_player([{"player_id": "t1", "decision_ids": ["d1"]}], "ct1")


def test_event_probability_uses_latest_same_round_row_before_event() -> None:
    event = {"tick": 180, "round_number": 2}
    timeline = [
        {"tick": 100, "round_number": 1, "ct_probability": 0.4, "t_probability": 0.6},
        {"tick": 120, "round_number": 2, "ct_probability": 0.5, "t_probability": 0.5},
        {"tick": 160, "round_number": 2, "ct_probability": 0.7, "t_probability": 0.3},
        {"tick": 200, "round_number": 2, "ct_probability": 0.9, "t_probability": 0.1},
    ]
    assert CLI._event_probability(event, timeline) == (0.7, 0.3)


def test_api_error_uses_fastapi_safe_detail() -> None:
    with pytest.raises(
        RuntimeError,
        match="agent-harness dependencies are not installed.*HTTP 503",
    ):
        CLI._raise_for_status(
            _Response(503, {"detail": "agent-harness dependencies are not installed"})
        )


class _Response:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"unexpected HTTP {self.status_code}")


class _FakeAsyncClient:
    calls: list[tuple[str, str, dict | None]] = []
    metadata_poll_count = 0
    fail_preparation = False

    def __init__(self, *, transport: object, base_url: str):
        self.transport = transport
        self.base_url = base_url

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def get(self, path: str):
        self.calls.append(("GET", path, None))
        if path == "/api/health":
            return _Response(200, {"status": "ok"})
        if path == "/api/analysis/analysis-1":
            self.metadata_poll_count += 1
            if self.fail_preparation:
                return _Response(200, {"status": "failed", "players_available": False})
            return _Response(200, {
                "status": "processing" if self.metadata_poll_count == 1 else "ready",
                "players_available": self.metadata_poll_count > 1,
            })
        if path.endswith("/players"):
            return _Response(200, {"players": [
                {"player_id": "no-contact", "display_name": "No Contact", "decision_ids": []},
                {"player_id": "t1", "display_name": "T One", "decision_ids": ["decision-1"]},
            ]})
        if path.endswith("/events"):
            return _Response(200, {})
        if path.endswith("/result"):
            return _Response(200, {
                "map_name": "de_mirage",
                "players": [{"player_id": "t1", "display_name": "T One"}],
                "selected_decision": {"contact_tick": 164},
                "key_events": [{
                    "tick": 164,
                    "round_number": 1,
                    "event_type": "damage",
                    "key_event_type": "first_damage_contact",
                    "participant_ids": ["t1"],
                    "is_key_event": True,
                }],
                "win_estimator": {"timeline": [
                    {"tick": 160, "round_number": 1, "ct_probability": 0.6, "t_probability": 0.4},
                ]},
            "coach_analysis": {"what_could_be_done_better": "Reset behind cover."},
                "replay_outcome": {
                    "eventual_winner": "T",
                    "round_score": {"CT": 12, "T": 16},
                },
            })
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path: str, *, json: dict):
        self.calls.append(("POST", path, json))
        if path == "/api/analysis/prepare":
            return _Response(202, {"analysis_id": "analysis-1"})
        if path.endswith("/run"):
            assert json == {"player_id": "t1"}
            return _Response(200, {})
        raise AssertionError(f"unexpected POST {path}")


def test_run_api_uses_public_route_sequence_and_selects_player() -> None:
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.metadata_poll_count = 0
    _FakeAsyncClient.fail_preparation = False
    fake_httpx = types.SimpleNamespace(
        AsyncClient=_FakeAsyncClient,
        ASGITransport=lambda *, app: object(),
    )
    fake_app_module = types.SimpleNamespace(create_app=lambda: object())
    replay = {"schema_version": 1, "replay_id": "demo"}

    with patch.dict(sys.modules, {"httpx": fake_httpx}), patch.dict(
        sys.modules, {"backend.app.main": fake_app_module}
    ), patch("builtins.input", return_value="1"):
        # The demo imports create_app from the module at call time.
        output = io.StringIO()
        with redirect_stdout(output):
            asyncio.run(CLI._run_api(replay, source="JSON: fixture", player_id=None))

    methods_and_paths = [(method, path) for method, path, _ in _FakeAsyncClient.calls]
    assert methods_and_paths == [
        ("GET", "/api/health"),
        ("POST", "/api/analysis/prepare"),
        ("GET", "/api/analysis/analysis-1"),
        ("GET", "/api/analysis/analysis-1"),
        ("GET", "/api/analysis/analysis-1/players"),
        ("POST", "/api/analysis/analysis-1/run"),
        ("GET", "/api/analysis/analysis-1/events"),
        ("GET", "/api/analysis/analysis-1/result"),
    ]
    assert "FIRST_DAMAGE_CONTACT" in output.getvalue()
    assert "Eventual winner: T (12-16)" in output.getvalue()
    assert "CT 60.0% | T 40.0%" in output.getvalue()
    assert "Better: Reset behind cover." in output.getvalue()


def test_run_api_stops_when_fastapi_reports_preparation_failure() -> None:
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.metadata_poll_count = 0
    _FakeAsyncClient.fail_preparation = True
    fake_httpx = types.SimpleNamespace(
        AsyncClient=_FakeAsyncClient,
        ASGITransport=lambda *, app: object(),
    )
    fake_app_module = types.SimpleNamespace(create_app=lambda: object())

    with patch.dict(sys.modules, {"httpx": fake_httpx}), patch.dict(
        sys.modules, {"backend.app.main": fake_app_module}
    ):
        with pytest.raises(RuntimeError, match="backend replay preparation failed"):
            asyncio.run(CLI._run_api({}, source="JSON: fixture", player_id="t1"))
