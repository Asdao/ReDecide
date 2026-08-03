"""Backend connector for Noah's deployed replay-analysis runtime.

The coach boundary accepts one normalized replay mapping and returns Noah's
combined analysis report.  It deliberately does not invent a provider prompt
or a RE:DECIDE ``DecisionCard``; those are separate contract layers.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol


class _ReplayAnalyzer(Protocol):
    def analyse_replay(self, replay: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]: ...


class NoahCoachError(RuntimeError):
    """Stable backend error for replay-analysis failures."""


class NoahCoachConnector:
    """Call the deployed Noah harness from the backend coach boundary."""

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

    def _runtime_or_load(self) -> _ReplayAnalyzer:
        if self._runtime is not None:
            return self._runtime
        try:
            workspace_root = Path(__file__).resolve().parents[3]
            model_src = workspace_root / "Noah" / "model" / "src"
            if str(model_src) not in sys.path:
                sys.path.insert(0, str(model_src))
            if str(workspace_root) not in sys.path:
                sys.path.insert(0, str(workspace_root))
            from cs2_sim import ModelConfig, ReplayModel

            # Keep the backend smoke path usable without native LightGBM;
            # deployments can pass ModelConfig(allow_fallback=False) to fail
            # closed when the full release is mandatory.
            config = self._model_config or ModelConfig(allow_fallback=True)
            self._runtime = ReplayModel.load(config)
            return self._runtime
        except Exception as exc:
            raise NoahCoachError(f"could not load Noah replay model: {exc}") from exc

    def analyse(self, replay: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        """Analyze one normalized replay mapping with the deployed harness."""

        if not isinstance(replay, Mapping):
            raise NoahCoachError("coach input must be a normalized replay object")
        try:
            report = self._runtime_or_load().analyse_replay(replay, **kwargs)
        except NoahCoachError:
            raise
        except Exception as exc:
            raise NoahCoachError(f"could not analyze replay for coaching: {exc}") from exc
        if not isinstance(report, dict) or report.get("report_type") != "combined_replay_analysis":
            raise NoahCoachError("Noah returned an invalid combined replay-analysis report")
        return report

    def analyze(self, replay: Mapping[str, Any], **kwargs: Any) -> dict[str, Any]:
        """American-English alias for :meth:`analyse`."""

        return self.analyse(replay, **kwargs)

    def analyse_json(self, payload: str | bytes, **kwargs: Any) -> dict[str, Any]:
        """Decode one JSON request body and analyze it."""

        try:
            replay = json.loads(payload)
        except (TypeError, json.JSONDecodeError) as exc:
            raise NoahCoachError(f"coach input is not valid JSON: {exc}") from exc
        return self.analyse(replay, **kwargs)


__all__ = ["NoahCoachConnector", "NoahCoachError"]
