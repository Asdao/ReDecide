"""Two-stage replay analysis orchestration.

The service owns a replay job after the upload.  Preparation indexes every
player and event once; selecting a player then filters the cached result and
invokes an injected coaching adapter.  Keeping the adapter injectable makes
the JSON fixture path deterministic while leaving the Pi/DeepSeek transport
outside the HTTP layer.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
import json
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

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
    status: str = "processing"
    selector: dict[str, Any] | None = None
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

    def prepare(self, replay: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(replay, Mapping):
            raise TypeError("replay must be a JSON object")
        analysis_id = uuid4().hex
        job = AnalysisJob(
            analysis_id=analysis_id,
            replay=dict(replay),
            log_path=self.log_dir / f"{analysis_id}.jsonl",
        )
        with self._jobs_lock:
            self._jobs[analysis_id] = job
        self._write_log(job, {"stage": "received", "progress": 0, "message": "Replay accepted."})
        self._executor.submit(self._prepare_worker, job)
        return self.metadata(analysis_id)

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
            if job.result is None:
                if job.status == "failed":
                    raise RuntimeError(job.error or "replay preparation failed")
                raise AnalysisNotReady("replay preparation is not complete")
            players = [item for item in job.result.get("players", []) if isinstance(item, Mapping)]
            selected = self._resolve_player(players, player_id=player_id, player_name=player_name)
            candidates = [
                item for item in job.result.get("decision_candidates", [])
                if isinstance(item, Mapping) and str(item.get("player_id")) == str(selected["player_id"])
            ]
            if not candidates:
                raise PlayerSelectionError("selected player has no first-contact decision candidate")
            candidate = dict(candidates[0])
            filtered = self._filter_for_player(job.result, str(selected["player_id"]))
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
                job.status = "failed"
                job.error = "coaching analysis failed"
                self._write_log(job, {"stage": "error", "progress": 100, "message": job.error})
                raise RuntimeError(job.error) from exc
            job.result = merged
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
                        job.result = dict(update["result"])
                        job.selector = {
                            "schema_version": "player_selector_v1",
                            "players": job.result.get("players", []),
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


__all__ = [
    "AnalysisNotFound",
    "AnalysisNotReady",
    "AnalysisService",
    "PlayerSelectionError",
]
