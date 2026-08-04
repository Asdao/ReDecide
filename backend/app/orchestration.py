"""Fixture and replay-job orchestration behind explicit integration boundaries.

``FixtureOrchestrator`` implements the frozen packet/intent/card fallback.
``AnalysisService`` preserves the incoming replay preparation job until its
internal report can be adapted to the frozen product contracts.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from backend.app.contracts import (
    APIErrorCode,
    AnalysisPreparationResponse,
    AnalysisResponse,
    AnalysisStage,
    AnalyzeJsonRequest,
    AnalyzeRequest,
    DecisionCard,
    DecisionPacket,
    NeutralDecisionSummary,
    SampleSummary,
    SamplesResponse,
)
from backend.app.errors import IntegrationError


FIXTURE_DIRECTORY = Path(__file__).parents[1] / "tests" / "fixtures"
FIXTURE_SAMPLE_ID = "fixture-mirage-01"
FIXTURE_ANALYSIS_ID = f"sample:{FIXTURE_SAMPLE_ID}"


def _load_fixture(name: str) -> dict:
    with (FIXTURE_DIRECTORY / name).open(encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


class FixtureOrchestrator:
    """Deterministic adapter that keeps integration moving before live systems."""

    def __init__(self) -> None:
        self._packet = DecisionPacket.model_validate(
            _load_fixture("decision_packet.valid.json")
        )
        self._card = DecisionCard.model_validate(
            _load_fixture("decision_card.valid.json")
        )
        self._sample = SampleSummary(
            sample_id=FIXTURE_SAMPLE_ID,
            display_name="Mirage post-contact example",
            description="Low-health repeat exposure after first contact",
            map=self._packet.map,
            players=[self._packet.player],
            recommended_player=self._packet.player,
            available=True,
        )

    def list_samples(self) -> SamplesResponse:
        return SamplesResponse(samples=[self._sample])

    def prepare(self, request: AnalyzeRequest) -> AnalysisPreparationResponse:
        sample_id = self._resolve_sample_id(request)
        if sample_id != self._sample.sample_id:
            raise IntegrationError(
                code=APIErrorCode.SAMPLE_NOT_FOUND,
                message=f"Unknown sample_id: {sample_id}",
                status_code=404,
            )

        if request.player is None:
            return AnalysisPreparationResponse(
                stage=AnalysisStage.PLAYER_SELECTION_REQUIRED,
                analysis_id=FIXTURE_ANALYSIS_ID,
                players=self._sample.players,
                decision_packet=None,
                neutral_summary=None,
            )

        if request.player not in self._sample.players:
            raise IntegrationError(
                code=APIErrorCode.PLAYER_NOT_FOUND,
                message=f"Player is not available for sample: {request.player}",
                status_code=404,
            )

        packet = self._packet.model_copy(deep=True)
        return AnalysisPreparationResponse(
            stage=AnalysisStage.INTENT_REQUIRED,
            analysis_id=FIXTURE_ANALYSIS_ID,
            players=self._sample.players,
            decision_packet=packet,
            neutral_summary=NeutralDecisionSummary(
                timestamp_seconds=packet.decision_open_seconds,
                text=packet.observed_action.description,
            ),
        )

    def analyze_json(self, request: AnalyzeJsonRequest) -> AnalysisResponse:
        if request.decision_packet.model_dump(mode="json") != self._packet.model_dump(
            mode="json"
        ):
            raise IntegrationError(
                code=APIErrorCode.MODEL_UNAVAILABLE,
                message=(
                    "The Day 1 fixture coach supports only the canonical fixture "
                    "packet; the live coach is not integrated"
                ),
                status_code=503,
                retryable=False,
                decision_id=request.decision_packet.decision_id,
            )

        card_payload = deepcopy(self._card.model_dump(mode="json"))
        card_payload["decision_id"] = request.decision_packet.decision_id
        card_payload["player_intent_summary"] = self._intent_summary(request)
        card = DecisionCard.model_validate(card_payload)
        return AnalysisResponse(
            decision_packet=request.decision_packet,
            decision_card=card,
        )

    @staticmethod
    def _resolve_sample_id(request: AnalyzeRequest) -> str:
        if request.sample_id is not None:
            return request.sample_id
        if request.analysis_id == FIXTURE_ANALYSIS_ID:
            return FIXTURE_SAMPLE_ID
        raise IntegrationError(
            code=APIErrorCode.INVALID_REQUEST,
            message=f"Unknown analysis_id: {request.analysis_id}",
            status_code=400,
        )

    @staticmethod
    def _intent_summary(request: AnalyzeJsonRequest) -> str:
        readable_tag = request.intent.tag.value.replace("_", " ").lower()
        if request.intent.text:
            return (
                f"The player selected {readable_tag} and explained: "
                f"{request.intent.text}"
            )
        return f"The player selected {readable_tag} without an additional note."
from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import threading
from typing import Any
from uuid import uuid4

from backend.app.coach.pi_connector import PiCoachError
from backend.app.replay.pipeline import merge_pi_output, stream_replay_pipeline


CoachAdapter = Callable[[Mapping[str, Any]], Mapping[str, Any] | str]


class AnalysisNotReady(RuntimeError):
    """Raised when a player is selected before replay preparation completes."""


class AnalysisNotFound(KeyError):
    """Raised when an unknown analysis job is requested."""


class PlayerSelectionError(ValueError):
    """Raised when a selected player is not present in the prepared replay."""


@dataclass
class AnalysisJob:
    analysis_id: str
    replay: Mapping[str, Any]
    log_path: Path
    source_replay_id: str | None = None
    status: str = "processing"
    selector: dict[str, Any] | None = None
    prepared_result: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    selected_player_id: str | None = None
    error: str | None = None
    updates: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class AnalysisService:
    """In-memory job store with durable per-job JSONL progress logs."""

    def __init__(
        self,
        log_dir: str | Path = "data/runtime/analysis-logs",
        *,
        coach_adapter: CoachAdapter | None = None,
        pipeline: Callable[..., Iterator[dict[str, Any]]] = stream_replay_pipeline,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.coach_adapter = coach_adapter
        self.pipeline = pipeline
        self._jobs: dict[str, AnalysisJob] = {}
        self._jobs_lock = threading.RLock()
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="replay-analysis")

    def prepare(self, replay: Mapping[str, Any], *, source_replay_id: str | None = None) -> dict[str, Any]:
        if not isinstance(replay, Mapping):
            raise TypeError("replay must be a JSON object")
        analysis_id = uuid4().hex
        job = AnalysisJob(
            analysis_id=analysis_id,
            replay=dict(replay),
            log_path=self.log_dir / f"{analysis_id}.jsonl",
            source_replay_id=source_replay_id,
        )
        with self._jobs_lock:
            self._jobs[analysis_id] = job
        self._write_log(job, {"stage": "received", "progress": 0, "message": "Replay accepted."})
        self._executor.submit(self._prepare_worker, job)
        return self.metadata(analysis_id)

    def source_replay_id(self, analysis_id: str) -> str | None:
        return self.get_job(analysis_id).source_replay_id

    def metadata(self, analysis_id: str) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            return {
                "analysis_id": job.analysis_id,
                "status": job.status,
                "players_available": job.selector is not None,
                "result_available": job.result is not None,
                "logs_url": f"/api/analysis/{job.analysis_id}/logs",
                "events_url": f"/api/analysis/{job.analysis_id}/events",
                "result_url": f"/api/analysis/{job.analysis_id}/result",
            }

    def players(self, analysis_id: str) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            if job.selector is None:
                raise AnalysisNotReady("player selector is not ready")
            return {
                "analysis_id": analysis_id,
                "status": job.status,
                "players": job.selector.get("players", []),
            }

    def select_player(self, analysis_id: str, *, player_id: str | None = None, player_name: str | None = None) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            if job.prepared_result is None:
                if job.status == "failed":
                    raise RuntimeError(job.error or "replay preparation failed")
                raise AnalysisNotReady("replay preparation is not complete")
            players = [item for item in job.prepared_result.get("players", []) if isinstance(item, Mapping)]
            selected = self._resolve_player(players, player_id=player_id, player_name=player_name)
            candidates = [
                item for item in job.prepared_result.get("decision_candidates", [])
                if isinstance(item, Mapping) and str(item.get("player_id")) == str(selected["player_id"])
            ]
            if not candidates:
                raise PlayerSelectionError("selected player has no first-contact decision candidate")
            candidate = dict(candidates[0])
            filtered = self._filter_for_player(job.prepared_result, str(selected["player_id"]))
            filtered["selected_decision"] = candidate
            job.selected_player_id = str(selected["player_id"])
            self._write_log(job, {
                "stage": "player_selected",
                "progress": 55,
                "player_id": str(selected["player_id"]),
                "message": "Player selection accepted.",
            })
            if self.coach_adapter is None:
                raise RuntimeError("coach adapter is not configured")
            self._write_log(job, {"stage": "calling_pi", "progress": 85, "message": "Generating coaching analysis."})
            try:
                pi_output = self.coach_adapter(filtered)
                merged = merge_pi_output(filtered, pi_output)
            except Exception as exc:  # noqa: BLE001 - stable API-facing failure
                # A prepared replay result is not a completed coaching result.
                # Clear it so /result cannot expose a partial success after Pi
                # fails and callers receive the stable failure response.
                job.result = None
                job.status = "failed"
                job.error = (
                    f"coaching analysis failed: {exc}"
                    if isinstance(exc, PiCoachError)
                    else "coaching analysis failed"
                )
                self._write_log(job, {"stage": "error", "progress": 100, "message": job.error})
                raise RuntimeError(job.error) from exc
            job.result = merged
            merged["replay_outcome"] = _replay_outcome(job.replay)
            job.status = "complete"
            self._write_log(job, {"stage": "complete", "progress": 100, "message": "Analysis complete.", "result_available": True})
            return dict(merged)

    def result(self, analysis_id: str) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            if job.result is None:
                if job.status == "failed":
                    raise RuntimeError(job.error or "analysis failed")
                raise AnalysisNotReady("analysis result is not ready")
            return dict(job.result)

    def logs(self, analysis_id: str) -> str:
        job = self.get_job(analysis_id)
        if not job.log_path.is_file():
            return ""
        return job.log_path.read_text(encoding="utf-8")

    def updates(self, analysis_id: str) -> list[dict[str, Any]]:
        job = self.get_job(analysis_id)
        with job.lock:
            return [dict(item) for item in job.updates]

    def get_job(self, analysis_id: str) -> AnalysisJob:
        with self._jobs_lock:
            try:
                return self._jobs[analysis_id]
            except KeyError as exc:
                raise AnalysisNotFound(analysis_id) from exc

    def _prepare_worker(self, job: AnalysisJob) -> None:
        try:
            for update in self.pipeline(job.replay):
                safe_update = {key: value for key, value in update.items() if key != "result"}
                # Preparation is the first half of the two-stage job. Keep a
                # single monotonic 0-100 scale once player coaching begins.
                if isinstance(safe_update.get("progress"), (int, float)):
                    safe_update["preparation_progress"] = safe_update["progress"]
                    safe_update["progress"] = min(50, int(safe_update["progress"] * 0.5))
                if safe_update.get("stage") == "complete":
                    safe_update["stage"] = "prepared"
                    safe_update["message"] = "Replay preparation is complete; select a player to continue."
                self._write_log(job, safe_update)
                if update.get("done") is True and isinstance(update.get("result"), Mapping):
                    with job.lock:
                        job.prepared_result = dict(update["result"])
                        job.selector = {
                            "schema_version": "player_selector_v1",
                            "players": job.prepared_result.get("players", []),
                        }
                        job.status = "ready"
        except Exception as exc:  # noqa: BLE001 - converted to stable job state
            with job.lock:
                job.status = "failed"
                job.error = "replay preparation failed"
            self._write_log(job, {"stage": "error", "progress": 100, "message": job.error})

    @staticmethod
    def _resolve_player(players: list[Mapping[str, Any]], *, player_id: str | None, player_name: str | None) -> Mapping[str, Any]:
        if player_id:
            matches = [item for item in players if str(item.get("player_id")) == player_id]
        elif player_name:
            matches = [item for item in players if str(item.get("display_name")) == player_name]
        else:
            raise PlayerSelectionError("player_id or player_name is required")
        if len(matches) != 1:
            raise PlayerSelectionError("player selection is missing or ambiguous")
        return matches[0]

    @staticmethod
    def _filter_for_player(result: Mapping[str, Any], player_id: str) -> dict[str, Any]:
        filtered = dict(result)
        for key in ("events", "key_events"):
            filtered[key] = [
                item for item in result.get(key, [])
                if isinstance(item, Mapping) and player_id in {str(value) for value in item.get("participant_ids", [])}
            ]
        filtered["decision_candidates"] = [
            item for item in result.get("decision_candidates", [])
            if isinstance(item, Mapping) and str(item.get("player_id")) == player_id
        ]
        # This remains deliberately global for the team win estimator.
        filtered["win_estimator"] = result.get("win_estimator")
        return filtered
    @staticmethod
    def _write_log(job: AnalysisJob, update: Mapping[str, Any]) -> None:
        payload = {"analysis_id": job.analysis_id, **dict(update)}
        with job.lock:
            job.updates.append(payload)
            with job.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _replay_outcome(replay: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize the eventual replay outcome after outcome-blind coaching."""

    scores = {"CT": 0, "T": 0}
    for round_info in replay.get("rounds", []):
        if not isinstance(round_info, Mapping):
            continue
        winner = _normalize_side(round_info.get("winner"))
        if winner is not None:
            scores[winner] += 1

    declared = replay.get("winner") or replay.get("match_winner")
    match = replay.get("match")
    if declared is None and isinstance(match, Mapping):
        declared = match.get("winner")
    eventual = _normalize_side(declared)
    if eventual is None and scores["CT"] != scores["T"]:
        eventual = max(scores, key=scores.get)
    return {
        "eventual_winner": eventual,
        "round_score": scores,
        "source": "declared_match_winner" if declared is not None else "round_score",
    }


def _normalize_side(value: Any) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"ct", "counter-terrorist", "counterterrorist"}:
        return "CT"
    if normalized in {"t", "terrorist"}:
        return "T"
    return None


__all__ = [
    "AnalysisNotFound",
    "AnalysisNotReady",
    "AnalysisService",
    "FixtureOrchestrator",
    "PlayerSelectionError",
]
