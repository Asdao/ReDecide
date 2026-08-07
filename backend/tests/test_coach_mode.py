"""Coach transport selection tests.

These tests exercise only the app-level mode switch.  Adapter behavior is
covered by the adapter-specific tests and is intentionally not duplicated.
"""

from __future__ import annotations

from unittest.mock import patch

from backend.app.main import _default_coach_adapter


def test_provider_configuration_defaults_to_http(monkeypatch) -> None:
    monkeypatch.delenv("REDECIDE_COACH_MODE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("HARNESS_MODEL_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with (
        patch("backend.app.main.HttpCoachAdapter") as http_adapter,
        patch("backend.app.main.PiCoachAdapter") as pi_adapter,
    ):
        result = _default_coach_adapter()

    http_adapter.assert_called_once_with()
    pi_adapter.assert_not_called()
    assert result is http_adapter.return_value


def test_explicit_pi_mode_wins_over_provider_configuration(monkeypatch) -> None:
    monkeypatch.setenv("REDECIDE_COACH_MODE", "pi")
    monkeypatch.setenv("HARNESS_MODEL_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with (
        patch("backend.app.main.HttpCoachAdapter") as http_adapter,
        patch("backend.app.main.PiCoachAdapter") as pi_adapter,
    ):
        result = _default_coach_adapter()

    pi_adapter.assert_called_once_with()
    http_adapter.assert_not_called()
    assert result is pi_adapter.return_value


def test_explicit_http_mode_does_not_require_process_key_at_selection_time(
    monkeypatch,
) -> None:
    monkeypatch.setenv("REDECIDE_COACH_MODE", "http")
    monkeypatch.delenv("HARNESS_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("HARNESS_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with (
        patch("backend.app.main.HttpCoachAdapter") as http_adapter,
        patch("backend.app.main.PiCoachAdapter") as pi_adapter,
    ):
        result = _default_coach_adapter()

    http_adapter.assert_called_once_with()
    pi_adapter.assert_not_called()
    assert result is http_adapter.return_value


def test_no_provider_configuration_preserves_pi_compatibility(monkeypatch) -> None:
    monkeypatch.delenv("REDECIDE_COACH_MODE", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("HARNESS_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("HARNESS_MODEL_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with (
        patch("backend.app.main.HttpCoachAdapter") as http_adapter,
        patch("backend.app.main.PiCoachAdapter") as pi_adapter,
    ):
        result = _default_coach_adapter()

    pi_adapter.assert_called_once_with()
    http_adapter.assert_not_called()
    assert result is pi_adapter.return_value
