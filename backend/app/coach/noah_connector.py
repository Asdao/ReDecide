"""Backend connector for Blackbox's deployed replay-analysis runtime.

The coach boundary accepts one normalized replay mapping and returns Blackbox's
combined analysis report.  It deliberately does not invent a provider prompt
or a RE:DECIDE ``DecisionCard``; those are separate contract layers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Protocol


class _ReplayAnalyzer(Protocol):
    def analyse_replay(self, replay: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]: ...


class NoahCoachError(RuntimeError):
    """Stable backend error for replay-analysis failures."""


class NoahCoachConnector:
    """Call the deployed Blackbox harness from the backend coach boundary."""

    def __init__(
        self,
        *,
        runtime: _ReplayAnalyzer | None = None,
        model_config: Any | None = None,
    ) -> None:
        if runtime is not None and model_config is not None:
            raise ValueError("pass either runtime or model_config, not both")
        self._runtime = runtime
        self._model_config = model_config

    def analyse(self, replay: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Analyze one normalized replay mapping with the deployed harness."""

        if not isinstance(replay, Mapping):
            raise NoahCoachError("coach input must be a normalized replay object")
        try:
            if self._runtime is not None:
                report = self._runtime.analyse_replay(replay, **kwargs)
            else:
                from Blackbox import analyze_replay

                options = dict(kwargs)
                if self._model_config is not None:
                    options.setdefault("model_config", self._model_config)
                report = analyze_replay(replay, **options)
        except NoahCoachError:
            raise
        except Exception as exc:
            raise NoahCoachError(f"could not analyze replay for coaching: {exc}") from exc
        if not isinstance(report, dict) or report.get("report_type") != "combined_replay_analysis":
            raise NoahCoachError("Blackbox returned an invalid combined replay-analysis report")
        return report

    def analyze(self, replay: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        """American-English alias for :meth:`analyse`."""

        return self.analyse(replay, **kwargs)

    def analyse_outcome_blind(
        self, replay: Mapping[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Return the harness report after removing future outcome fields.

        This is the safe projection for an API/UI boundary.  The regular
        ``analyse`` method remains available for internal evaluation reports
        that intentionally retain terminal match context.
        """

        report = self.analyse(replay, **kwargs)
        from Blackbox.training.analysis_report import outcome_blind_report

        return outcome_blind_report(report)

    def analyze_outcome_blind(
        self, replay: Mapping[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """American-English alias for :meth:`analyse_outcome_blind`."""

        return self.analyse_outcome_blind(replay, **kwargs)

    def analyse_json(self, payload: str | bytes, **kwargs: Any) -> dict[str, Any]:
        """Decode one JSON request body and analyze it."""

        try:
            replay = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise NoahCoachError(f"coach input is not valid JSON: {exc}") from exc
        return self.analyse(replay, **kwargs)


__all__ = ["NoahCoachConnector", "NoahCoachError"]
