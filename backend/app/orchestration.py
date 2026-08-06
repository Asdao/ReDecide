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
from urllib.parse import unquote
from uuid import uuid4

from backend.app.analysis_store import (
    load_analysis_result,
    load_analysis_state,
    save_analysis_result,
    save_analysis_state,
)
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
    player_runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    updates: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class AnalysisService:
    """Replay preparation plus repeatable per-player coaching runs.

    Jobs stay in memory for active requests, while prepared state and completed
    player results are cached as atomic JSON artifacts for restart recovery.
    """

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
        self.analysis_store_dir = self.log_dir / "analysis-state"
        self._restore_persisted_jobs()

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
        self._persist_job(job)
        self._executor.submit(self._prepare_worker, job)
        return self.metadata(analysis_id)

    def source_replay_id(self, analysis_id: str) -> str | None:
        return self.get_job(analysis_id).source_replay_id

    def metadata(self, analysis_id: str) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            player_runs = {
                player_id: {
                    "status": str(run.get("status") or "unknown"),
                    "result_available": run.get("result") is not None,
                    **({"run_id": run["run_id"]} if run.get("run_id") else {}),
                }
                for player_id, run in job.player_runs.items()
            }
            return {
                "analysis_id": job.analysis_id,
                "status": job.status,
                "players_available": job.selector is not None,
                "result_available": any(
                    run.get("result") is not None for run in job.player_runs.values()
                ) or job.result is not None,
                "selected_player_id": job.selected_player_id,
                "player_runs": player_runs,
                "logs_url": f"/api/analysis/{job.analysis_id}/logs",
                "events_url": f"/api/analysis/{job.analysis_id}/events",
                "result_url": f"/api/analysis/{job.analysis_id}/result",
            }

    def players(self, analysis_id: str) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            if job.selector is None:
                raise AnalysisNotReady("player selector is not ready")
            selectable = []
            for item in job.selector.get("players", []):
                if not isinstance(item, Mapping):
                    continue
                player = dict(item)
                player["analysis_available"] = bool(player.get("decision_ids"))
                player["analysis_status"] = job.player_runs.get(
                    str(player.get("player_id")), {}
                ).get("status", "not_started")
                selectable.append(player)
            return {
                "analysis_id": analysis_id,
                "status": job.status,
                "players": selectable,
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
            if self.coach_adapter is None:
                raise RuntimeError("coach adapter is not configured")
            selected_player_id = str(selected["player_id"])
            previous_run = job.player_runs.get(selected_player_id)
            if previous_run and previous_run.get("status") == "running":
                raise AnalysisNotReady("coaching is already running for this player")
            candidate = dict(candidates[0])
            filtered = self._filter_for_player(job.prepared_result, selected_player_id)
            filtered["selected_decision"] = candidate
            run_id = uuid4().hex
            job.selected_player_id = selected_player_id
            job.status = "coaching"
            job.error = None
            job.result = None
            job.player_runs[selected_player_id] = {
                "run_id": run_id,
                "status": "running",
                "result": None,
                "error": None,
            }
            self._persist_job(job)
            self._write_log(job, {
                "stage": "player_selected",
                "progress": 55,
                "player_id": selected_player_id,
                "run_id": run_id,
                "message": "Player selection accepted.",
            })
            self._write_log(job, {
                "stage": "calling_pi",
                "progress": 85,
                "player_id": selected_player_id,
                "run_id": run_id,
                "message": "Generating coaching analysis.",
            })
            coach_adapter = self.coach_adapter

        # Provider calls can take seconds or minutes. Do not hold the job lock
        # while waiting, so metadata/events and other player runs remain live.
        try:
            pi_output = coach_adapter(filtered)
            merged = merge_pi_output(filtered, pi_output)
        except Exception as exc:  # noqa: BLE001 - stable API-facing failure
            with job.lock:
                error = (
                    f"coaching analysis failed: {exc}"
                    if isinstance(exc, PiCoachError)
                    else "coaching analysis failed"
                )
                job.player_runs[selected_player_id] = {
                    "run_id": run_id,
                    "status": "failed",
                    "result": None,
                    "error": error,
                }
                job.error = error
                job.status = "failed"
                self._persist_job(job)
                self._write_log(job, {
                    "stage": "error",
                    "progress": 100,
                    "player_id": selected_player_id,
                    "run_id": run_id,
                    "message": error,
                })
                raise RuntimeError(error) from exc
        with job.lock:
            job.result = merged
            merged["replay_outcome"] = _replay_outcome(job.replay)
            job.player_runs[selected_player_id] = {
                "run_id": run_id,
                "status": "complete",
                "result": merged,
                "error": None,
            }
            job.status = "complete"
            self._persist_job(job)
            self._write_log(job, {
                "stage": "complete",
                "progress": 100,
                "player_id": selected_player_id,
                "run_id": run_id,
                "message": "Analysis complete.",
                "result_available": True,
            })
            return dict(merged)

    def result(self, analysis_id: str, *, player_id: str | None = None) -> dict[str, Any]:
        job = self.get_job(analysis_id)
        with job.lock:
            if player_id is not None:
                player_run = job.player_runs.get(str(player_id))
                if player_run is None:
                    raise PlayerSelectionError("no analysis run exists for this player")
                player_result = player_run.get("result")
                if player_result is not None:
                    return dict(player_result)
                if player_run.get("status") == "failed":
                    raise RuntimeError(str(player_run.get("error") or "analysis failed"))
                raise AnalysisNotReady("analysis result is not ready")
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

    def _persist_job(self, job: AnalysisJob) -> None:
        """Persist restart-safe state without making the cache a hard dependency."""

        with job.lock:
            state = {
                "schema_version": "analysis_state_v1",
                "analysis_id": job.analysis_id,
                "replay": dict(job.replay),
                "source_replay_id": job.source_replay_id,
                "status": job.status,
                "selector": job.selector,
                "prepared_result": job.prepared_result,
                "selected_player_id": job.selected_player_id,
                "error": job.error,
                "player_runs": {
                    player_id: {
                        "run_id": run.get("run_id"),
                        "status": run.get("status"),
                        "error": run.get("error"),
                        "result_available": run.get("result") is not None,
                    }
                    for player_id, run in job.player_runs.items()
                },
            }
            try:
                save_analysis_state(job.analysis_id, state, root=self.analysis_store_dir)
                save_analysis_result(
                    job.analysis_id,
                    {
                        "schema_version": "analysis_results_v1",
                        "analysis_id": job.analysis_id,
                        "results_by_player": {
                            player_id: run["result"]
                            for player_id, run in job.player_runs.items()
                            if run.get("result") is not None
                        },
                    },
                    root=self.analysis_store_dir,
                )
            except (OSError, TypeError, ValueError):
                # A local cache must not turn a successful coach invocation into
                # an API failure. The in-memory job remains authoritative.
                return

    def _restore_persisted_jobs(self) -> None:
        """Restore prepared/completed jobs when the service process restarts."""

        if not self.analysis_store_dir.is_dir():
            return
        for state_path in self.analysis_store_dir.glob("*/state.json"):
            analysis_id = unquote(state_path.parent.name)
            try:
                state = load_analysis_state(analysis_id, root=self.analysis_store_dir)
                replay = state.get("replay")
                if not isinstance(replay, Mapping):
                    continue
                job = AnalysisJob(
                    analysis_id=analysis_id,
                    replay=dict(replay),
                    log_path=self.log_dir / f"{analysis_id}.jsonl",
                    source_replay_id=state.get("source_replay_id"),
                    status=str(state.get("status") or "ready"),
                    selector=state.get("selector") if isinstance(state.get("selector"), dict) else None,
                    prepared_result=(
                        state.get("prepared_result")
                        if isinstance(state.get("prepared_result"), dict)
                        else None
                    ),
                    selected_player_id=state.get("selected_player_id"),
                    error=state.get("error"),
                )
                persisted_runs = state.get("player_runs")
                if isinstance(persisted_runs, Mapping):
                    for player_id, run in persisted_runs.items():
                        if not isinstance(run, Mapping):
                            continue
                        job.player_runs[str(player_id)] = {
                            "run_id": run.get("run_id"),
                            "status": run.get("status"),
                            "result": None,
                            "error": run.get("error"),
                        }
                try:
                    results = load_analysis_result(
                        analysis_id, root=self.analysis_store_dir
                    )
                except (FileNotFoundError, ValueError):
                    results = {}
                results_by_player = results.get("results_by_player")
                if isinstance(results_by_player, Mapping):
                    for player_id, result in results_by_player.items():
                        if player_id in job.player_runs:
                            job.player_runs[player_id]["result"] = result
                if job.selected_player_id in job.player_runs:
                    job.result = job.player_runs[job.selected_player_id].get("result")
                if job.status == "coaching":
                    # A process restart cannot resume a live provider call.
                    # Prepared replay data remains reusable for a fresh run.
                    for run in job.player_runs.values():
                        if run.get("status") == "running":
                            run["status"] = "failed"
                            run["error"] = "coaching run interrupted by restart"
                    job.status = "ready" if job.prepared_result is not None else "failed"
                with self._jobs_lock:
                    self._jobs[analysis_id] = job
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

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
                        self._persist_job(job)
        except Exception as exc:  # noqa: BLE001 - converted to stable job state
            with job.lock:
                job.status = "failed"
                job.error = "replay preparation failed"
                self._persist_job(job)
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
