"""Outcome-blind coaching for a player's stated intent.

The engine is deliberately a domain boundary rather than a second replay
parser.  Its caller supplies an already parsed, player-scoped analysis result;
the engine selects the exact requested decision, projects only evidence known
at that decision's opening tick, and validates the model response against that
evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from backend.app.coach.pi_connector import PiCoachError
from backend.app.replay.pipeline import _decode_pi_output

MAX_PROMPT_BYTES = 64 * 1024


class IntentCoachingError(RuntimeError):
    """Base class for failures at the intent-coaching domain boundary."""


class IntentDecisionNotFoundError(IntentCoachingError):
    """The requested decision does not belong to the requested player."""


class IntentInsufficientEvidenceError(IntentCoachingError):
    """The replay does not contain enough bounded evidence to coach safely."""


class IntentProviderUnavailableError(IntentCoachingError):
    """The configured language-model provider could not produce a response."""


class IntentProviderTimeoutError(IntentProviderUnavailableError):
    """The configured language-model provider exceeded its time limit."""


class IntentMalformedOutputError(IntentCoachingError):
    """The provider output did not satisfy the grounded response contract."""


class PromptProvider(Protocol):
    """Small provider seam shared by the Pi and HTTP adapters."""

    def run_prompt(self, prompt: str) -> str | Mapping[str, Any]: ...


class _IntentModelOutput(BaseModel):
    """Strict shape required from the language model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    intent_feasibility: str = Field(min_length=1)
    coordination_gap: str = Field(min_length=1)
    recommended_cs2_adjustment: str = Field(min_length=1)
    in_depth_coaching: str = Field(min_length=1)
    facts_referenced: list[str] = Field(min_length=1)

    @field_validator(
        "intent_feasibility",
        "coordination_gap",
        "recommended_cs2_adjustment",
        "in_depth_coaching",
    )
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("text fields cannot be blank")
        return cleaned

    @field_validator("facts_referenced")
    @classmethod
    def facts_must_be_unique_and_nonblank(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("facts_referenced cannot contain blank IDs")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("facts_referenced IDs must be unique")
        return cleaned


class IntentCoachingEngine:
    """Evaluate one stated intent using evidence known at one exact decision."""

    def __init__(self, coach_adapter: PromptProvider | None = None) -> None:
        self.coach_adapter = coach_adapter

    def evaluate_intent(
        self,
        pipeline_result: Mapping[str, Any],
        user_intent: str,
        player_id: str | None = None,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        """Return grounded coaching or raise a typed, fail-closed exception."""

        clean_intent = str(user_intent).strip()
        if not clean_intent:
            raise IntentInsufficientEvidenceError("player intent cannot be blank")

        selected, valid_evidence_ids, open_tick = self._extract_decision_context(
            pipeline_result,
            decision_id=decision_id,
            player_id=player_id,
        )
        prompt = self.build_intent_prompt(selected, clean_intent, open_tick)

        if self.coach_adapter is None:
            raise IntentProviderUnavailableError("intent coaching provider is not configured")

        try:
            raw_response = self.coach_adapter.run_prompt(prompt)
        except Exception as exc:
            if _is_timeout(exc):
                raise IntentProviderTimeoutError("intent coaching provider timed out") from exc
            raise IntentProviderUnavailableError(
                "intent coaching provider is unavailable"
            ) from exc

        output = self._validate_model_output(raw_response, valid_evidence_ids)
        return {
            "decision_id": str(selected["decision_id"]),
            "player_id": str(selected["player_id"]),
            "user_intent": clean_intent,
            "intent_feasibility": output.intent_feasibility,
            "coordination_gap": output.coordination_gap,
            "recommended_cs2_adjustment": output.recommended_cs2_adjustment,
            "in_depth_coaching": output.in_depth_coaching,
            "knowledge_cutoff_tick": open_tick,
            "facts_referenced": output.facts_referenced,
        }

    def build_intent_prompt(
        self,
        selected: Mapping[str, Any],
        user_intent: str,
        open_tick: int,
    ) -> str:
        """Build a compact prompt containing only the bounded evidence projection."""

        evidence = selected.get("known_before_decision")
        known_events = selected.get("_intent_known_events")
        if not isinstance(evidence, list) or not isinstance(known_events, list):
            raise IntentInsufficientEvidenceError(
                "intent context has not been bounded and validated"
            )

        player_id = str(selected.get("player_id") or "")
        opponent_id = str(selected.get("opponent_id") or "")
        aliases = {player_id: "player_01"}
        if opponent_id and opponent_id != player_id:
            aliases[opponent_id] = "player_02"

        bounded_payload = {
            "schema_version": "intent_coach_input_v1",
            "decision": {
                # The provider never needs the raw Steam ID embedded in the
                # product decision ID; the API response restores it outside
                # this model-visible payload.
                "decision_id": "decision_001",
                "round_number": selected.get("round_number"),
                "player_id": "player_01",
                "side": selected.get("side"),
                "role": selected.get("role"),
                "event_category": selected.get("event_category"),
                "decision_open_tick": open_tick,
                "contact_tick": selected.get("contact_tick"),
                "opponent_id": aliases.get(opponent_id, "unknown"),
            },
            "known_before_decision": _anonymize(evidence, aliases),
            "known_events": _anonymize(known_events, aliases),
            "knowledge_cutoff_tick": open_tick,
            "limitations": [
                "The intent is a subjective player statement, not replay telemetry.",
                "Voice communications and unobserved information are unavailable.",
                "No event after knowledge_cutoff_tick is available.",
            ],
        }

        prompt = (
            "You are an outcome-blind Counter-Strike 2 tactical coach.\n"
            "Use only the JSON evidence supplied below. Do not infer later kills, "
            "deaths, the round winner, the match result, voice communication, or "
            "any fact not represented by an evidence_id. Treat PLAYER_INTENT as a "
            "subjective post-hoc explanation, not confirmed telemetry. Every entry "
            "in facts_referenced must be one of the supplied evidence_id values.\n"
            f"PLAYER_INTENT={json.dumps(user_intent, ensure_ascii=True)}\n"
            "DECISION_CONTEXT="
            f"{json.dumps(bounded_payload, ensure_ascii=True, separators=(',', ':'))}\n"
            "Return ONLY one JSON object with exactly these fields: "
            '{"intent_feasibility":string,"coordination_gap":string,'
            '"recommended_cs2_adjustment":string,"in_depth_coaching":string,'
            '"facts_referenced":array_of_evidence_id_strings}'
        )
        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise IntentInsufficientEvidenceError(
                "bounded intent context exceeds the provider size limit"
            )
        return prompt

    def _extract_decision_context(
        self,
        pipeline_result: Mapping[str, Any],
        *,
        decision_id: str | None = None,
        player_id: str | None = None,
    ) -> tuple[dict[str, Any], set[str], int]:
        """Select the exact decision and retain only facts at/before its cutoff."""

        requested_decision = str(decision_id or "").strip()
        requested_player = str(player_id or "").strip()
        if not requested_decision or not requested_player:
            raise IntentDecisionNotFoundError(
                "both decision_id and player_id are required for intent coaching"
            )

        selected: dict[str, Any] | None = None
        for candidate in _decision_candidates(pipeline_result):
            if (
                str(candidate.get("decision_id") or "") == requested_decision
                and str(candidate.get("player_id") or "") == requested_player
            ):
                selected = dict(candidate)
                break
        if selected is None:
            raise IntentDecisionNotFoundError(
                "requested decision does not exist for the selected player"
            )

        open_tick = _strict_nonnegative_int(selected.get("decision_open_tick"))
        if open_tick is None:
            raise IntentInsufficientEvidenceError(
                "selected decision has no valid decision_open_tick"
            )

        round_number = _strict_nonnegative_int(selected.get("round_number"))
        known_evidence: list[dict[str, Any]] = []
        known_events: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        raw_evidence = selected.get("known_before_decision")
        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if not isinstance(item, Mapping):
                    continue
                evidence_id = str(item.get("evidence_id") or "").strip()
                tick = _strict_nonnegative_int(item.get("tick"))
                if not evidence_id or tick is None or tick > open_tick:
                    continue
                if evidence_id in seen_ids:
                    continue
                known_evidence.append(dict(item))
                seen_ids.add(evidence_id)

        raw_events = pipeline_result.get("key_events")
        if isinstance(raw_events, list):
            for event in raw_events:
                if not isinstance(event, Mapping):
                    continue
                event_id = str(event.get("event_id") or "").strip()
                tick = _strict_nonnegative_int(event.get("tick"))
                event_round = _strict_nonnegative_int(event.get("round_number"))
                participants = [str(value) for value in event.get("participant_ids", [])]
                if (
                    not event_id
                    or tick is None
                    or tick > open_tick
                    or (round_number is not None and event_round != round_number)
                    or requested_player not in participants
                ):
                    continue
                if event_id in seen_ids:
                    continue
                known_events.append(
                    {
                        "evidence_id": event_id,
                        "tick": tick,
                        "round_number": event.get("round_number"),
                        "event_type": event.get("event_type"),
                        "key_event_type": event.get("key_event_type"),
                        "participant_ids": participants,
                        "is_coaching_anchor": bool(event.get("is_coaching_anchor")),
                    }
                )
                seen_ids.add(event_id)

        if not seen_ids:
            raise IntentInsufficientEvidenceError(
                "no citable replay evidence exists at or before the decision cutoff"
            )

        selected["known_before_decision"] = known_evidence
        selected["_intent_known_events"] = known_events
        return selected, seen_ids, open_tick

    @staticmethod
    def _validate_model_output(
        raw_response: str | Mapping[str, Any],
        valid_evidence_ids: set[str],
    ) -> _IntentModelOutput:
        try:
            payload = _decode_pi_output(raw_response)
            output = _IntentModelOutput.model_validate(payload)
        except (PiCoachError, TypeError, ValueError, ValidationError) as exc:
            raise IntentMalformedOutputError(
                "intent coaching provider returned malformed output"
            ) from exc

        unsupported = set(output.facts_referenced) - valid_evidence_ids
        if unsupported:
            raise IntentMalformedOutputError(
                "intent coaching provider referenced unsupported evidence IDs"
            )
        return output


def _decision_candidates(pipeline_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return all decision objects carried by either live production shape."""

    candidates: list[Mapping[str, Any]] = []
    analyses = pipeline_result.get("analyses")
    if isinstance(analyses, list):
        for item in analyses:
            if not isinstance(item, Mapping):
                continue
            selected = item.get("selected_decision")
            if isinstance(selected, Mapping):
                candidates.append(selected)

    selected_many = pipeline_result.get("selected_decisions")
    if isinstance(selected_many, list):
        candidates.extend(item for item in selected_many if isinstance(item, Mapping))

    selected = pipeline_result.get("selected_decision")
    if isinstance(selected, Mapping):
        candidates.append(selected)

    raw_candidates = pipeline_result.get("decision_candidates")
    if isinstance(raw_candidates, list):
        candidates.extend(item for item in raw_candidates if isinstance(item, Mapping))
    return candidates


def _strict_nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _is_timeout(exc: BaseException) -> bool:
    """Recognize timeouts even when a transport adapter wraps the root cause."""

    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = current.__class__.__name__.lower()
        if isinstance(current, TimeoutError) or "timeout" in name or "timed out" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


def _anonymize(value: Any, aliases: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for raw, alias in aliases.items():
            if raw:
                result = result.replace(raw, alias)
        return result
    if isinstance(value, list):
        return [_anonymize(item, aliases) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _anonymize(item, aliases) for key, item in value.items()}
    return value


__all__ = [
    "IntentCoachingEngine",
    "IntentCoachingError",
    "IntentDecisionNotFoundError",
    "IntentInsufficientEvidenceError",
    "IntentProviderUnavailableError",
    "IntentProviderTimeoutError",
    "IntentMalformedOutputError",
]
