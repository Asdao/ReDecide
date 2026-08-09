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
import math
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.coach.pi_connector import PiCoachError
from backend.app.coach.intent_claims import (
    IntentClaimValidationError,
    GroundedEvidenceClaim,
    ProviderEvidenceClaim,
    render_public_evidence_summary,
    validate_evidence_claims,
)
from backend.app.coach.intent_leak_guard import (
    FORBIDDEN_INTERNAL_TOKENS,
    PublicCoachingProseError,
    validate_public_coaching_payload,
)
from backend.app.coach.intent_public_text import translate_provider_aliases
from backend.app.replay.pipeline import _decode_pi_output

MAX_PROMPT_BYTES = 64 * 1024
MAX_REACTION_SECONDS = 3.0

IntentCategory = Literal[
    "GATHER_INFORMATION",
    "ESCAPE_RESET",
    "TAKE_DUEL",
    "HOLD_FOR_SUPPORT",
    "CREATE_SPACE_WITH_UTILITY",
    "REPOSITION",
    "UNCLEAR",
]

_FORBIDDEN_OUTCOME_EVENT_TYPES = {
    "death",
    "kill",
    "match_end",
    "round_end",
    "round_result",
    "round_winner",
}
_NON_SUBSTANTIVE_DECISION_SIGNALS = {"no_action_window_observation"}
_DECISION_SIGNAL_STATEMENTS = {
    "contact_initiator": "You initiated the first exchange of damage.",
    "displacement_above_threshold": "You changed position immediately after contact.",
    "displacement_below_threshold": "You barely changed position immediately after contact.",
    "no_action_window_observation": (
        "The replay could not establish a clear immediate response."
    ),
    "zone_changed": "You moved into a different area immediately after contact.",
}
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
    """Strict, non-prose decision shape required from the language model.

    The provider selects bounded categories and links them to evidence IDs. It
    never authors public factual prose; the backend renders that prose from its
    own evidence statements after validation.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    # Current telemetry cannot deterministically prove arbitrary free-text
    # intent feasibility or team coordination. Keep both conservative until a
    # reviewed rule layer exists; the model still selects the tactical focus.
    intent_assessment: Literal["NOT_ESTABLISHED"]
    coordination_assessment: Literal["NOT_ESTABLISHED"]
    recommended_adjustment: Literal[
        "RESET_BEHIND_COVER",
        "HOLD_FOR_SUPPORT",
        "CONTROLLED_REENGAGEMENT",
        "MAINTAIN_CROSSHAIR_WHILE_DISENGAGING",
        "USE_AVAILABLE_UTILITY",
        "REASSESS_BEFORE_REENGAGING",
    ]
    evidence_claims: list[ProviderEvidenceClaim] = Field(min_length=1)


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
        intent_category = _classify_stated_intent(clean_intent)

        selected, valid_evidence_ids, cutoff_tick = self._extract_decision_context(
            pipeline_result,
            decision_id=decision_id,
            player_id=player_id,
        )
        if intent_category == "UNCLEAR":
            return _clarification_response(
                selected=selected,
                clean_intent=clean_intent,
                cutoff_tick=cutoff_tick,
            )

        prompt = self.build_intent_prompt(
            selected,
            clean_intent,
            cutoff_tick,
            intent_category=intent_category,
        )

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

        output, grounded_claims = self._validate_model_output(
            raw_response,
            valid_evidence_ids,
            substantive_evidence_ids=set(selected.get("_intent_substantive_ids", [])),
            available_utility=set(selected.get("_intent_available_utility", [])),
            authoritative_evidence=_authoritative_evidence(selected),
        )
        _validate_adjustment_for_intent(
            intent_category,
            output.recommended_adjustment,
        )
        public_response = _render_public_response(
            output,
            grounded_claims=grounded_claims,
            available_utility=set(selected.get("_intent_available_utility", [])),
            intent_category=intent_category,
        )
        result = {
            "decision_id": str(selected["decision_id"]),
            "player_id": str(selected["player_id"]),
            "user_intent": clean_intent,
            **public_response,
            "knowledge_cutoff_tick": cutoff_tick,
            "facts_referenced": list(
                dict.fromkeys(claim.evidence_id for claim in grounded_claims)
            ),
        }
        return _validate_public_result(result, selected=selected, cutoff_tick=cutoff_tick)

    def build_intent_prompt(
        self,
        selected: Mapping[str, Any],
        user_intent: str,
        cutoff_tick: int,
        *,
        intent_category: IntentCategory | None = None,
    ) -> str:
        """Build a compact prompt containing only the bounded evidence projection."""

        evidence = selected.get("known_before_decision")
        known_events = selected.get("_intent_known_events")
        reaction_evidence = selected.get("_intent_reaction_evidence")
        if (
            not isinstance(evidence, list)
            or not isinstance(known_events, list)
            or not isinstance(reaction_evidence, list)
        ):
            raise IntentInsufficientEvidenceError(
                "intent context has not been bounded and validated"
            )

        player_id = str(selected.get("player_id") or "")
        opponent_id = str(selected.get("opponent_id") or "")
        aliases = _context_aliases(player_id, opponent_id, known_events)

        resolved_intent_category = intent_category or _classify_stated_intent(
            user_intent
        )
        bounded_payload = {
            "schema_version": "intent_coach_input_v1",
            "stated_intent_category": resolved_intent_category,
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
                "map_name": selected.get("_intent_map_name"),
                "decision_open_tick": selected.get("decision_open_tick"),
                "contact_tick": selected.get("contact_tick"),
                "action_close_tick": selected.get("action_close_tick"),
                "opponent_id": aliases.get(opponent_id, "unknown"),
            },
            "known_before_decision": _anonymize(evidence, aliases),
            "known_events": _anonymize(known_events, aliases),
            "bounded_reaction_evidence": _anonymize(reaction_evidence, aliases),
            "evidence_capabilities": sorted(selected.get("_intent_capabilities", [])),
            "knowledge_cutoff_tick": cutoff_tick,
            "limitations": [
                "The intent is a subjective player statement, not replay telemetry.",
                "Voice communications and unobserved information are unavailable.",
                "No event after knowledge_cutoff_tick is available.",
                "A missing field means unknown, not that the event or resource did not exist.",
                "Kill, death, round-result, and match-result events are excluded.",
            ],
        }

        prompt = (
            "You are an outcome-blind Counter-Strike 2 tactical coach.\n"
            "Use only the JSON evidence supplied below. Do not infer later kills, "
            "deaths, the round winner, the match result, voice communication, or "
            "any fact not represented by an evidence_id. Treat PLAYER_INTENT as a "
            "subjective post-hoc explanation, not confirmed telemetry. Every entry "
            "in evidence_claims must reference one supplied evidence_id. "
            "evidence_claims must include at least one ID from "
            "bounded_reaction_evidence or known_before_decision, not only the "
            "first-damage anchor. "
            "Do not convert missing evidence into a negative claim: say 'not "
            "established by the available evidence' instead of claiming there was "
            "no movement, utility, support, cover, or communication. Do not invent "
            "map geometry, line of sight, teammate readiness, utility, or CS2 items. "
            "Only recommend utility listed as available_utility in the evidence. "
            "Keep general advice explicitly conditional and separate from replay "
            "observations. Use plain ASCII punctuation. If feasibility or "
            "coordination cannot be established, say so directly.\n"
            f"PLAYER_INTENT={json.dumps(user_intent, ensure_ascii=True)}\n"
            "DECISION_CONTEXT="
            f"{json.dumps(bounded_payload, ensure_ascii=True, separators=(',', ':'))}\n"
            "Return ONLY one JSON object with exactly these fields and enum values: "
            '{"intent_assessment":"NOT_ESTABLISHED",'
            '"coordination_assessment":"NOT_ESTABLISHED",'
            '"recommended_adjustment":"RESET_BEHIND_COVER|HOLD_FOR_SUPPORT|'
            'CONTROLLED_REENGAGEMENT|MAINTAIN_CROSSHAIR_WHILE_DISENGAGING|'
            'USE_AVAILABLE_UTILITY|REASSESS_BEFORE_REENGAGING",'
            '"evidence_claims":[{"evidence_id":string,"supports":'
            '"intent_feasibility|coordination_gap|recommended_cs2_adjustment|'
            'in_depth_coaching"}]}. Include mappings for the recommendation and '
            "in-depth coaching only. Intent feasibility and team coordination are "
            "not established by the available telemetry. The same evidence ID may support "
            "different fields, but do not repeat the same ID/field pair. Do not "
            "return coaching prose or factual claim text; "
            "the backend renders public text from the selected evidence IDs. Choose "
            "a recommended_adjustment that is tactically compatible with the supplied "
            "stated_intent_category."
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

        contact_tick = _strict_nonnegative_int(selected.get("contact_tick"))
        if contact_tick is None:
            contact_tick = open_tick
        action_close_tick = _strict_nonnegative_int(selected.get("action_close_tick"))
        if action_close_tick is None:
            action_close_tick = contact_tick

        source_replay = pipeline_result.get("_intent_source_replay")
        replay = source_replay if isinstance(source_replay, Mapping) else None
        tick_rate = _replay_tick_rate(replay)
        max_reaction_ticks = max(1, int(round(tick_rate * MAX_REACTION_SECONDS)))
        if (
            contact_tick < open_tick
            or action_close_tick < contact_tick
            or action_close_tick > contact_tick + max_reaction_ticks
        ):
            raise IntentInsufficientEvidenceError(
                "selected decision has an invalid or unsafe action window"
            )
        cutoff_tick = action_close_tick

        round_number = _strict_nonnegative_int(selected.get("round_number"))
        known_evidence: list[dict[str, Any]] = []
        known_events: list[dict[str, Any]] = []
        reaction_evidence: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        substantive_ids: set[str] = set()
        capabilities: set[str] = set()
        available_utility: set[str] = set()

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
                substantive_ids.add(evidence_id)

        raw_events = pipeline_result.get("key_events")
        if isinstance(raw_events, list):
            for event in raw_events:
                if not isinstance(event, Mapping):
                    continue
                event_id = str(event.get("event_id") or "").strip()
                tick = _strict_nonnegative_int(event.get("tick"))
                event_round = _strict_nonnegative_int(event.get("round_number"))
                event_type = str(event.get("event_type") or "").lower()
                participants = [str(value) for value in event.get("participant_ids", [])]
                if (
                    not event_id
                    or not event_type
                    or tick is None
                    or tick > cutoff_tick
                    or (round_number is not None and event_round != round_number)
                    or requested_player not in participants
                    or event_type in _FORBIDDEN_OUTCOME_EVENT_TYPES
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

                if tick > contact_tick or not bool(event.get("is_coaching_anchor")):
                    substantive_ids.add(event_id)

        decision_items, decision_substantive = _project_decision_evidence(
            selected, cutoff_tick
        )
        telemetry_items, telemetry_capabilities, telemetry_utility = (
            _project_replay_evidence(replay, selected, cutoff_tick, tick_rate)
            if replay is not None
            else ([], set(), set())
        )
        for item in [*decision_items, *telemetry_items]:
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in seen_ids:
                continue
            reaction_evidence.append(item)
            seen_ids.add(evidence_id)
        substantive_ids.update(decision_substantive)
        substantive_ids.update(
            str(item["evidence_id"])
            for item in telemetry_items
            if item.get("evidence_id") in seen_ids
        )
        capabilities.update(telemetry_capabilities)
        available_utility.update(telemetry_utility)

        if not seen_ids or not substantive_ids:
            raise IntentInsufficientEvidenceError(
                "insufficient citable replay evidence exists within the bounded decision window"
            )

        selected["known_before_decision"] = known_evidence
        selected["_intent_known_events"] = known_events
        selected["_intent_reaction_evidence"] = reaction_evidence
        selected["_intent_substantive_ids"] = sorted(substantive_ids & seen_ids)
        selected["_intent_capabilities"] = sorted(capabilities)
        selected["_intent_available_utility"] = sorted(available_utility)
        selected["_intent_map_name"] = _map_name(pipeline_result, replay)
        return selected, seen_ids, cutoff_tick

    @staticmethod
    def _validate_model_output(
        raw_response: str | Mapping[str, Any],
        valid_evidence_ids: set[str],
        *,
        substantive_evidence_ids: set[str],
        available_utility: set[str],
        authoritative_evidence: list[dict[str, Any]],
    ) -> tuple[_IntentModelOutput, list[GroundedEvidenceClaim]]:
        try:
            payload = _decode_pi_output(raw_response)
            output = _IntentModelOutput.model_validate(payload)
        except (PiCoachError, TypeError, ValueError, ValidationError) as exc:
            raise IntentMalformedOutputError(
                "intent coaching provider returned malformed output"
            ) from exc

        claim_ids = [claim.evidence_id for claim in output.evidence_claims]
        unsupported = set(claim_ids) - valid_evidence_ids
        if unsupported:
            raise IntentMalformedOutputError(
                "intent coaching provider referenced unsupported evidence IDs"
            )
        if not set(claim_ids) & substantive_evidence_ids:
            raise IntentMalformedOutputError(
                "intent coaching provider did not cite substantive bounded evidence"
            )
        if (
            output.recommended_adjustment == "USE_AVAILABLE_UTILITY"
            and not available_utility
        ):
            raise IntentMalformedOutputError(
                "intent coaching provider recommended unavailable utility"
            )
        try:
            grounded_claims = validate_evidence_claims(
                [claim.model_dump() for claim in output.evidence_claims],
                authoritative_evidence,
            )
        except IntentClaimValidationError as exc:
            raise IntentMalformedOutputError(
                "intent coaching provider returned invalid claim-to-evidence mappings"
            ) from exc
        _validate_claim_targets(
            output,
            grounded_claims,
            substantive_evidence_ids=substantive_evidence_ids,
        )
        return output, grounded_claims


_INTENT_ASSESSMENT_TEXT = {
    "NOT_ESTABLISHED": (
        "Replay telemetry does not by itself establish whether your stated intent "
        "was feasible."
    ),
}
_INTENT_PHRASES: dict[IntentCategory, tuple[str, ...]] = {
    "GATHER_INFORMATION": (
        "gather information",
        "get information",
        "wanted information",
        "get info",
        "gather info",
        "spot the enemy",
        "check the angle",
        "see where",
        "find out",
        "scout",
        "information",
        "info",
    ),
    "ESCAPE_RESET": (
        "did not want to fight",
        "didn t want to fight",
        "avoid the fight",
        "avoid fighting",
        "get away",
        "fall back",
        "disengage",
        "retreat",
        "escape",
        "reset",
        "survive",
    ),
    "TAKE_DUEL": (
        "re-engage",
        "reengage",
        "take the duel",
        "take a duel",
        "challenge",
        "fight",
        "swing",
        "duel",
        "kill",
    ),
    "HOLD_FOR_SUPPORT": (
        "wait for support",
        "wait for my teammate",
        "teammate would trade",
        "play for the trade",
        "hold for support",
        "support",
        "teammate",
        "trade",
        "wait",
        "hold",
    ),
    "CREATE_SPACE_WITH_UTILITY": (
        "create space",
        "use utility",
        "molotov",
        "grenade",
        "utility",
        "flash",
        "smoke",
        "nade",
    ),
    "REPOSITION": (
        "change angle",
        "move position",
        "reposition",
        "rotate",
    ),
    "UNCLEAR": (),
}
_INTENT_PUBLIC_GOAL: dict[IntentCategory, str] = {
    "GATHER_INFORMATION": "gather information",
    "ESCAPE_RESET": "escape and reset",
    "TAKE_DUEL": "take the duel",
    "HOLD_FOR_SUPPORT": "wait for support",
    "CREATE_SPACE_WITH_UTILITY": "create space with utility",
    "REPOSITION": "reposition",
    "UNCLEAR": "clarify the tactical goal",
}
_INTENT_COACHING_TEXT: dict[IntentCategory, str] = {
    "GATHER_INFORMATION": (
        "Keep the exposure brief with a shoulder or jiggle peek, preserve a path "
        "back to cover, and reset once you confirm the opponent's position."
    ),
    "ESCAPE_RESET": (
        "Prioritize the shortest route to hard cover, keep your crosshair on the "
        "danger angle, and reassess before exposing yourself again."
    ),
    "TAKE_DUEL": (
        "Commit to one controlled angle: stop accurately, keep the crosshair at "
        "head level, and avoid widening the fight into multiple threats."
    ),
    "HOLD_FOR_SUPPORT": (
        "Delay the next exposure until support can trade the contact, and choose a "
        "position that lets both players fight the same threat."
    ),
    "CREATE_SPACE_WITH_UTILITY": (
        "Use utility only when it can safely block, delay, or displace the opponent, "
        "then move while that advantage is active."
    ),
    "REPOSITION": (
        "Move through hard cover, preserve your crosshair on the likely follow-up "
        "angle, and avoid crossing the same exposed line twice."
    ),
    "UNCLEAR": "Clarify the tactical goal before requesting coaching.",
}
_ALLOWED_ADJUSTMENTS: dict[IntentCategory, frozenset[str]] = {
    "GATHER_INFORMATION": frozenset(
        {
            "RESET_BEHIND_COVER",
            "MAINTAIN_CROSSHAIR_WHILE_DISENGAGING",
            "REASSESS_BEFORE_REENGAGING",
        }
    ),
    "ESCAPE_RESET": frozenset(
        {
            "RESET_BEHIND_COVER",
            "MAINTAIN_CROSSHAIR_WHILE_DISENGAGING",
            "USE_AVAILABLE_UTILITY",
            "REASSESS_BEFORE_REENGAGING",
        }
    ),
    "TAKE_DUEL": frozenset(
        {
            "CONTROLLED_REENGAGEMENT",
            "HOLD_FOR_SUPPORT",
            "USE_AVAILABLE_UTILITY",
            "REASSESS_BEFORE_REENGAGING",
        }
    ),
    "HOLD_FOR_SUPPORT": frozenset(
        {"HOLD_FOR_SUPPORT", "RESET_BEHIND_COVER", "REASSESS_BEFORE_REENGAGING"}
    ),
    "CREATE_SPACE_WITH_UTILITY": frozenset(
        {"USE_AVAILABLE_UTILITY", "RESET_BEHIND_COVER", "REASSESS_BEFORE_REENGAGING"}
    ),
    "REPOSITION": frozenset(
        {
            "RESET_BEHIND_COVER",
            "HOLD_FOR_SUPPORT",
            "MAINTAIN_CROSSHAIR_WHILE_DISENGAGING",
            "REASSESS_BEFORE_REENGAGING",
        }
    ),
    "UNCLEAR": frozenset(),
}
_DEFAULT_ADJUSTMENT: dict[IntentCategory, str] = {
    "GATHER_INFORMATION": "REASSESS_BEFORE_REENGAGING",
    "ESCAPE_RESET": "RESET_BEHIND_COVER",
    "TAKE_DUEL": "CONTROLLED_REENGAGEMENT",
    "HOLD_FOR_SUPPORT": "HOLD_FOR_SUPPORT",
    "CREATE_SPACE_WITH_UTILITY": "USE_AVAILABLE_UTILITY",
    "REPOSITION": "MAINTAIN_CROSSHAIR_WHILE_DISENGAGING",
    "UNCLEAR": "REASSESS_BEFORE_REENGAGING",
}


def _classify_stated_intent(user_intent: str) -> IntentCategory:
    """Map explicit player wording to a conservative tactical goal."""

    normalized = re.sub(r"[^a-z0-9]+", " ", user_intent.lower()).strip()
    matches: list[tuple[int, int, IntentCategory]] = []
    for category, phrases in _INTENT_PHRASES.items():
        for phrase in phrases:
            match = re.search(
                rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])",
                normalized,
            )
            if match is not None:
                # Prefer the earliest explicit goal; for the same position,
                # prefer the more specific phrase.
                matches.append((match.start(), -len(phrase), category))
    if not matches:
        return "UNCLEAR"
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return matches[0][2]


def _validate_adjustment_for_intent(
    intent_category: IntentCategory,
    adjustment: str,
) -> None:
    if adjustment not in _ALLOWED_ADJUSTMENTS[intent_category]:
        raise IntentMalformedOutputError(
            "intent coaching provider selected an adjustment incompatible with the stated goal"
        )


def _clarification_response(
    *,
    selected: Mapping[str, Any],
    clean_intent: str,
    cutoff_tick: int,
) -> dict[str, Any]:
    clarification = (
        "Tell us whether you were trying to gather information, escape, take the "
        "duel, wait for support, use utility, or reposition."
    )
    result = {
        "decision_id": str(selected["decision_id"]),
        "player_id": str(selected["player_id"]),
        "user_intent": clean_intent,
        "intent_feasibility": "Your tactical goal is not clear enough to evaluate.",
        "coordination_gap": (
            "Replay telemetry does not establish communication, readiness, or a "
            "team coordination plan."
        ),
        "recommended_cs2_adjustment": clarification,
        "in_depth_coaching": clarification,
        "knowledge_cutoff_tick": cutoff_tick,
        "facts_referenced": [],
    }
    return _validate_public_result(result, selected=selected, cutoff_tick=cutoff_tick)


def _validate_public_result(
    result: dict[str, Any],
    *,
    selected: Mapping[str, Any],
    cutoff_tick: int,
) -> dict[str, Any]:
    try:
        validate_public_coaching_payload(
            result,
            forbidden_replay_coordinates={
                value
                for value in (
                    _strict_nonnegative_int(selected.get("decision_open_tick")),
                    _strict_nonnegative_int(selected.get("contact_tick")),
                    _strict_nonnegative_int(selected.get("action_close_tick")),
                    cutoff_tick,
                )
                if value is not None
            },
        )
    except PublicCoachingProseError as exc:
        raise IntentMalformedOutputError(
            "intent coaching public prose failed the leak guard"
        ) from exc
    return result


_COORDINATION_ASSESSMENT_TEXT = {
    "NOT_ESTABLISHED": (
        "Replay telemetry does not establish communication, readiness, or a team "
        "coordination plan."
    ),
}
_ADJUSTMENT_TEXT = {
    "RESET_BEHIND_COVER": (
        "Break contact into hard cover, stabilize, and recheck the angle before "
        "re-engaging."
    ),
    "HOLD_FOR_SUPPORT": (
        "Delay the next peek until a teammate can support or trade the engagement."
    ),
    "CONTROLLED_REENGAGEMENT": (
        "If you re-engage, counter-strafe, pre-aim one angle, and take a controlled duel."
    ),
    "MAINTAIN_CROSSHAIR_WHILE_DISENGAGING": (
        "Keep your crosshair on the danger angle while moving into cover instead of "
        "turning away from the threat."
    ),
    "USE_AVAILABLE_UTILITY": (
        "Use an available grenade to create separation before repositioning, when the "
        "throw can be made safely."
    ),
    "REASSESS_BEFORE_REENGAGING": (
        "Pause in safety, reassess teammate support and the danger angle, then decide "
        "whether to re-engage."
    ),
}


def _validate_claim_targets(
    output: _IntentModelOutput,
    grounded_claims: list[GroundedEvidenceClaim],
    *,
    substantive_evidence_ids: set[str],
) -> None:
    """Require each asserted category to have an explicit evidence mapping."""

    targets = {claim.supports for claim in grounded_claims}
    required = {"recommended_cs2_adjustment", "in_depth_coaching"}
    if not required.issubset(targets):
        raise IntentMalformedOutputError(
            "intent coaching provider omitted a required claim-to-evidence mapping"
        )
    if any(
        claim.supports in {"intent_feasibility", "coordination_gap"}
        for claim in grounded_claims
    ):
        raise IntentMalformedOutputError(
            "intent coaching provider mapped an assessment that telemetry cannot establish"
        )
    for target in required:
        if not any(
            claim.supports == target
            and claim.evidence_id in substantive_evidence_ids
            for claim in grounded_claims
        ):
            raise IntentMalformedOutputError(
                "intent coaching provider did not ground each public field in substantive evidence"
            )
    if output.recommended_adjustment == "USE_AVAILABLE_UTILITY" and not any(
        claim.supports == "recommended_cs2_adjustment"
        and claim.evidence_id == "telemetry:contact-state"
        for claim in grounded_claims
    ):
        raise IntentMalformedOutputError(
            "utility advice did not cite the bounded inventory evidence"
        )


def _render_public_response(
    output: _IntentModelOutput,
    *,
    grounded_claims: list[GroundedEvidenceClaim],
    available_utility: set[str],
    intent_category: IntentCategory,
) -> dict[str, str]:
    """Render all public prose from backend-owned templates and evidence."""

    if output.recommended_adjustment == "USE_AVAILABLE_UTILITY" and not available_utility:
        raise IntentMalformedOutputError(
            "intent coaching provider recommended unavailable utility"
        )
    try:
        evidence_summary = render_public_evidence_summary(
            grounded_claims,
            max_items=2,
        )
    except IntentClaimValidationError as exc:
        raise IntentMalformedOutputError(
            "intent coaching evidence could not be rendered safely"
        ) from exc

    evidence_text = evidence_summary.removeprefix("Replay evidence: ").strip()
    adjustment = _ADJUSTMENT_TEXT[output.recommended_adjustment]
    contextual_adjustment = _INTENT_COACHING_TEXT[intent_category]
    if output.recommended_adjustment != _DEFAULT_ADJUSTMENT[intent_category]:
        contextual_adjustment = f"{contextual_adjustment} {adjustment}"
    public_goal = _INTENT_PUBLIC_GOAL[intent_category]
    response = {
        "intent_feasibility": _INTENT_ASSESSMENT_TEXT[output.intent_assessment],
        "coordination_gap": _COORDINATION_ASSESSMENT_TEXT[
            output.coordination_assessment
        ],
        "recommended_cs2_adjustment": contextual_adjustment,
        "in_depth_coaching": (
            f"{evidence_text} Because you said you wanted to {public_goal}, "
            f"{contextual_adjustment[0].lower()}{contextual_adjustment[1:]}"
        ),
    }
    return {
        field_name: translate_provider_aliases(value)
        for field_name, value in response.items()
    }


def _authoritative_evidence(selected: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Collect backend-rendered evidence statements in their bounded order.

    Upstream ``statement`` strings are never reused here. Each supported
    evidence kind is rendered from typed values so schema labels, aliases, and
    disguised replay coordinates cannot enter public prose.
    """

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    replay_coordinates = {
        value
        for value in (
            _strict_nonnegative_int(selected.get("decision_open_tick")),
            _strict_nonnegative_int(selected.get("contact_tick")),
            _strict_nonnegative_int(selected.get("action_close_tick")),
        )
        if value is not None
    }
    for field_name in (
        "known_before_decision",
        "_intent_known_events",
        "_intent_reaction_evidence",
    ):
        items = selected.get(field_name)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            evidence_id = str(item.get("evidence_id") or "").strip()
            if not evidence_id or evidence_id in seen:
                continue
            statement = _typed_public_evidence_statement(
                item,
                field_name=field_name,
                forbidden_replay_coordinates=replay_coordinates,
            )
            evidence.append(
                {"evidence_id": evidence_id, "statement": statement}
            )
            seen.add(evidence_id)
    evidence_priority = {
        "telemetry:contact-state": 0,
        "telemetry:reaction-movement": 1,
        "telemetry:teammate-spacing": 2,
        "decision:observed-action": 3,
    }
    evidence.sort(
        key=lambda item: (
            evidence_priority.get(
                str(item["evidence_id"]),
                4 if str(item["evidence_id"]).startswith("decision:signal:") else 5,
            ),
            str(item["evidence_id"]),
        )
    )
    return evidence


def _typed_public_evidence_statement(
    item: Mapping[str, Any],
    *,
    field_name: str,
    forbidden_replay_coordinates: set[int],
) -> str:
    """Render one evidence item without trusting an upstream prose field."""

    if field_name == "known_before_decision":
        return "The replay captured relevant context from before the engagement."

    if field_name == "_intent_known_events":
        event_type = _safe_public_label(
            item.get("event_type"),
            fallback="replay event",
            forbidden_replay_coordinates=forbidden_replay_coordinates,
        )
        return (
            f"The replay recorded a {event_type} involving you during the immediate response."
        )

    kind = str(item.get("kind") or "").strip().lower()
    value = item.get("value") if isinstance(item.get("value"), Mapping) else {}
    if kind == "observed_action":
        action = str(item.get("value") or "").strip().lower()
        if re.fullmatch(r"[a-z0-9_-]{1,64}", action):
            public_actions = {
                "hold": "You held your position immediately after contact.",
                "reset": "You disengaged immediately after contact.",
                "reset_reposition": "You repositioned immediately after contact.",
                "re_engage": "You re-engaged immediately after contact.",
                "re-engage": "You re-engaged immediately after contact.",
            }
            return public_actions.get(
                action,
                "The replay captured your immediate response after contact.",
            )
    if kind == "action_signal":
        signal = str(item.get("value") or "").strip().lower()
        return _DECISION_SIGNAL_STATEMENTS.get(
            signal,
            "The replay captured part of your immediate response.",
        )
    if kind == "contact_state":
        role = str(value.get("role") or "").lower()
        place = _safe_public_label(
            value.get("place"),
            fallback="",
            forbidden_replay_coordinates=forbidden_replay_coordinates,
        )
        health_before = _number(value.get("health_before"))
        health_after = _number(value.get("health_after_contact"))
        if role == "victim" and health_before is not None and health_after is not None:
            return (
                f"You took first damage on {place or 'the recorded area'}, and your "
                f"health changed from {health_before:g} to {health_after:g}."
            )
        if role == "victim":
            return f"You took first damage on {place or 'the recorded area'}."
        if role == "attacker":
            return f"You initiated first damage from {place or 'the recorded area'}."
        if place:
            return f"First damage contact happened while you were on {place}."
        return "The first exchange of damage was recorded."
    if kind == "reaction_movement":
        displacement = _number(value.get("displacement_units"))
        if displacement is not None:
            start_place = _safe_public_label(
                value.get("start_place"),
                fallback="an unnamed region",
                forbidden_replay_coordinates=forbidden_replay_coordinates,
            )
            end_place = _safe_public_label(
                value.get("end_place"),
                fallback="an unnamed region",
                forbidden_replay_coordinates=forbidden_replay_coordinates,
            )
            if displacement <= 10:
                return "You remained almost stationary immediately after contact."
            if start_place != end_place:
                return f"You moved from {start_place} to {end_place} immediately after contact."
            if displacement <= 100:
                return "You moved only a short distance immediately after contact."
            return "You made a clear reposition immediately after contact."
    if kind == "teammate_spacing":
        nearest = _number(value.get("nearest_living_teammate_distance_units"))
        nearby = _strict_nonnegative_int(value.get("living_teammates_within_500_units"))
        if nearest is not None and nearby is not None:
            if nearby == 0:
                return "No living teammate was recorded nearby at contact."
            if nearby == 1:
                return "One living teammate was recorded nearby at contact."
            return f"{nearby} living teammates were recorded nearby at contact."
    return "The replay captured part of your immediate response."


def _safe_public_label(
    value: Any,
    *,
    fallback: str,
    forbidden_replay_coordinates: set[int],
) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9 .'-]{1,64}", text):
        return fallback
    if re.search(r"\bplayer(?:[- _]?\d{1,3})\b", text, flags=re.IGNORECASE):
        return fallback
    compact = re.sub(r"[^a-z0-9]", "", text.lower())
    forbidden_compact = {
        re.sub(r"[^a-z0-9]", "", token.lower())
        for token in FORBIDDEN_INTERNAL_TOKENS
    }
    forbidden_compact.update(
        {"contacttick", "evidenceids", "knownbeforedecision", "playerevent"}
    )
    if compact in forbidden_compact:
        return fallback
    digits = re.sub(r"\D", "", text)
    if digits and int(digits) in forbidden_replay_coordinates:
        return fallback
    try:
        numeric_value = float(text.replace(" ", ""))
    except ValueError:
        numeric_value = None
    if (
        numeric_value is not None
        and numeric_value.is_integer()
        and int(numeric_value) in forbidden_replay_coordinates
    ):
        return fallback
    return text


def _project_decision_evidence(
    selected: Mapping[str, Any], cutoff_tick: int
) -> tuple[list[dict[str, Any]], set[str]]:
    """Turn deterministic action-classifier fields into citable evidence."""

    items: list[dict[str, Any]] = []
    substantive: set[str] = set()
    action = str(selected.get("observed_action") or "").strip().lower()
    if action and action != "unknown" and re.fullmatch(r"[a-z0-9_\-]{1,64}", action):
        evidence_id = "decision:observed-action"
        items.append(
            {
                "evidence_id": evidence_id,
                "tick": cutoff_tick,
                "source": "deterministic_action_classifier",
                "kind": "observed_action",
                "value": action,
                "statement": (
                    f"The bounded action classifier labeled the immediate reaction as {action}."
                ),
            }
        )
        substantive.add(evidence_id)

    raw_signals = selected.get("evidence")
    if isinstance(raw_signals, list):
        for index, raw_signal in enumerate(raw_signals, start=1):
            signal = str(raw_signal or "").strip().lower()
            if not signal or not re.fullmatch(r"[a-z0-9_\-]{1,80}", signal):
                continue
            evidence_id = f"decision:signal:{index}"
            statement = _DECISION_SIGNAL_STATEMENTS.get(
                signal,
                f"The deterministic action classifier emitted the signal {signal}.",
            )
            items.append(
                {
                    "evidence_id": evidence_id,
                    "tick": cutoff_tick,
                    "source": "deterministic_action_classifier",
                    "kind": "action_signal",
                    "value": signal,
                    "statement": statement,
                }
            )
            if signal not in _NON_SUBSTANTIVE_DECISION_SIGNALS:
                substantive.add(evidence_id)
    return items, substantive


def _project_replay_evidence(
    replay: Mapping[str, Any],
    selected: Mapping[str, Any],
    cutoff_tick: int,
    tick_rate: float,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Project only own-state and teammate-spacing telemetry for one action window."""

    player_id = str(selected.get("player_id") or "")
    opponent_id = str(selected.get("opponent_id") or "")
    role = str(selected.get("role") or "").lower()
    side = str(selected.get("side") or "").lower()
    round_number = _strict_nonnegative_int(selected.get("round_number"))
    contact_tick = _strict_nonnegative_int(selected.get("contact_tick"))
    if not player_id or contact_tick is None:
        return [], set(), set()

    items: list[dict[str, Any]] = []
    capabilities: set[str] = set()
    available_utility: set[str] = set()
    contact_record = _matching_contact_damage(
        replay,
        player_id=player_id,
        opponent_id=opponent_id,
        role=role,
        round_number=round_number,
        contact_tick=contact_tick,
    )

    before_tick: Mapping[str, Any] | None = None
    after_tick: Mapping[str, Any] | None = None
    teammate_frames: dict[str, Mapping[str, Any]] = {}
    ticks = replay.get("ticks")
    if isinstance(ticks, list):
        oldest_team_tick = max(0, contact_tick - max(1, int(round(tick_rate))))
        for raw_tick in ticks:
            if not isinstance(raw_tick, Mapping):
                continue
            tick = _strict_nonnegative_int(raw_tick.get("tick"))
            if tick is None or tick > cutoff_tick:
                continue
            tick_round = _strict_nonnegative_int(raw_tick.get("round_num"))
            if round_number is not None and tick_round != round_number:
                continue
            tick_player = str(raw_tick.get("steamid") or "")
            if tick_player == player_id:
                if tick <= contact_tick and (
                    before_tick is None
                    or tick > int(before_tick.get("tick", -1))
                ):
                    before_tick = raw_tick
                if tick >= contact_tick and (
                    after_tick is None
                    or tick > int(after_tick.get("tick", -1))
                ):
                    after_tick = raw_tick
            elif (
                oldest_team_tick <= tick <= contact_tick
                and str(raw_tick.get("side") or "").lower() == side
                and _positive_number(raw_tick.get("health"))
            ):
                previous = teammate_frames.get(tick_player)
                if tick_player and (
                    previous is None or tick > int(previous.get("tick", -1))
                ):
                    teammate_frames[tick_player] = raw_tick

    own_contact = _own_contact_fields(contact_record, role) if contact_record else {}
    inventory = own_contact.get("inventory")
    if not isinstance(inventory, list) and before_tick is not None:
        inventory = before_tick.get("inventory")
    if isinstance(inventory, list):
        available_utility.update(_canonical_utility(item) for item in inventory)
        available_utility.discard("")
        capabilities.add("utility_inventory")

    contact_value: dict[str, Any] = {
        "role": role,
        "side": side,
        "contact_tick": contact_tick,
    }
    for key in (
        "place",
        "health_before",
        "health_after_contact",
        "armor_before",
        "armor_after_contact",
        "damage_health",
        "damage_armor",
        "hitgroup",
        "weapon",
    ):
        if own_contact.get(key) is not None:
            contact_value[key] = own_contact[key]
    if isinstance(inventory, list):
        contact_value["inventory"] = [str(item) for item in inventory[:16]]
        contact_value["available_utility"] = sorted(available_utility)
    if before_tick is not None:
        contact_value.setdefault("place", before_tick.get("place"))
        contact_value["snapshot_tick"] = before_tick.get("tick")
        contact_value.setdefault("health_before", before_tick.get("health"))
        contact_value.setdefault("armor_before", before_tick.get("armor"))

    if len(contact_value) > 3:
        statement_bits = ["First damage contact occurred"]
        if contact_value.get("place"):
            statement_bits.append(f"in the parser region {contact_value['place']}")
        if contact_value.get("health_before") is not None and contact_value.get("health_after_contact") is not None:
            statement_bits.append(
                f"with health changing from {contact_value['health_before']} to {contact_value['health_after_contact']}"
            )
        items.append(
            {
                "evidence_id": "telemetry:contact-state",
                "tick": contact_tick,
                "source": "demo_parser",
                "kind": "contact_state",
                "value": contact_value,
                "statement": "; ".join(statement_bits) + ".",
            }
        )
        capabilities.add("contact_state")
        if contact_value.get("place"):
            capabilities.add("own_position")
        if contact_value.get("health_before") is not None:
            capabilities.add("own_health")

    start_position = _contact_position(contact_record, role)
    if start_position is None:
        start_position = _tick_position(before_tick)
    end_position = _tick_position(after_tick)
    if start_position is not None and end_position is not None and after_tick is not None:
        displacement = round(math.dist(start_position, end_position), 1)
        reaction_value: dict[str, Any] = {
            "start_tick": contact_tick,
            "end_tick": after_tick.get("tick"),
            "displacement_units": displacement,
            "start_place": contact_value.get("place"),
            "end_place": after_tick.get("place"),
        }
        end_health = _number(after_tick.get("health"))
        if end_health is not None and end_health > 0:
            reaction_value["health_at_window_end"] = end_health
        items.append(
            {
                "evidence_id": "telemetry:reaction-movement",
                "tick": int(after_tick.get("tick", cutoff_tick)),
                "source": "demo_parser",
                "kind": "reaction_movement",
                "value": reaction_value,
                "statement": (
                    f"During the bounded reaction window, the player moved {displacement} units"
                    f" from {reaction_value.get('start_place') or 'an unnamed region'}"
                    f" to {reaction_value.get('end_place') or 'an unnamed region'}."
                ),
            }
        )
        capabilities.add("reaction_movement")

    if start_position is not None and teammate_frames:
        distances: list[float] = []
        for frame in teammate_frames.values():
            position = _tick_position(frame)
            if position is not None:
                distances.append(math.dist(start_position, position))
        if distances:
            nearest = round(min(distances), 1)
            nearby = sum(distance <= 500.0 for distance in distances)
            teammate_label = "teammate was" if nearby == 1 else "teammates were"
            items.append(
                {
                    "evidence_id": "telemetry:teammate-spacing",
                    "tick": contact_tick,
                    "source": "demo_parser",
                    "kind": "teammate_spacing",
                    "value": {
                        "nearest_living_teammate_distance_units": nearest,
                        "living_teammates_within_500_units": nearby,
                    },
                    "statement": (
                        f"At contact, the nearest living teammate was {nearest} units away; "
                        f"{nearby} living {teammate_label} within 500 units."
                    ),
                }
            )
            capabilities.add("teammate_spacing")

    return items, capabilities, available_utility


def _matching_contact_damage(
    replay: Mapping[str, Any],
    *,
    player_id: str,
    opponent_id: str,
    role: str,
    round_number: int | None,
    contact_tick: int,
) -> Mapping[str, Any] | None:
    damages = replay.get("damages")
    if not isinstance(damages, list):
        return None
    player_field = "victim_steamid" if role == "victim" else "attacker_steamid"
    opponent_field = "attacker_steamid" if role == "victim" else "victim_steamid"
    for damage in damages:
        if not isinstance(damage, Mapping):
            continue
        if _strict_nonnegative_int(damage.get("tick")) != contact_tick:
            continue
        if round_number is not None and _strict_nonnegative_int(damage.get("round_num")) != round_number:
            continue
        if str(damage.get(player_field) or "") != player_id:
            continue
        if opponent_id and str(damage.get(opponent_field) or "") != opponent_id:
            continue
        return damage
    return None


def _own_contact_fields(record: Mapping[str, Any], role: str) -> dict[str, Any]:
    if role == "victim":
        return {
            "place": record.get("victim_place"),
            "health_before": _number(record.get("victim_health")),
            "health_after_contact": _number(record.get("health")),
            "armor_before": _number(record.get("victim_armor")),
            "armor_after_contact": _number(record.get("armor")),
            "damage_health": _number(record.get("dmg_health_real") or record.get("dmg_health")),
            "damage_armor": _number(record.get("dmg_armor")),
            "hitgroup": record.get("hitgroup"),
            "inventory": record.get("victim_inventory"),
        }
    return {
        "place": record.get("attacker_place"),
        "health_before": _number(record.get("attacker_health")),
        "armor_before": _number(record.get("attacker_armor")),
        "damage_health": _number(record.get("dmg_health_real") or record.get("dmg_health")),
        "damage_armor": _number(record.get("dmg_armor")),
        "hitgroup": record.get("hitgroup"),
        "weapon": record.get("weapon"),
        "inventory": record.get("attacker_inventory"),
    }


def _contact_position(record: Mapping[str, Any] | None, role: str) -> tuple[float, float, float] | None:
    if record is None:
        return None
    prefix = "victim" if role == "victim" else "attacker"
    values = tuple(_number(record.get(f"{prefix}_{axis}")) for axis in ("X", "Y", "Z"))
    if any(value is None for value in values):
        return None
    return values  # type: ignore[return-value]


def _tick_position(frame: Mapping[str, Any] | None) -> tuple[float, float, float] | None:
    if frame is None:
        return None
    values = tuple(_number(frame.get(axis)) for axis in ("X", "Y", "Z"))
    if any(value is None for value in values):
        return None
    return values  # type: ignore[return-value]


def _canonical_utility(value: Any) -> str:
    text = str(value or "").lower()
    if "smoke" in text:
        return "smoke"
    if "flash" in text:
        return "flash"
    if "molotov" in text:
        return "molotov"
    if "incendiary" in text:
        return "incendiary"
    if "high explosive" in text or "he grenade" in text:
        return "he"
    if "decoy" in text:
        return "decoy"
    return ""


def _replay_tick_rate(replay: Mapping[str, Any] | None) -> float:
    if replay is not None:
        value = _number(replay.get("tick_rate"))
        if value is not None and 16.0 <= value <= 256.0:
            return value
    return 64.0


def _map_name(
    pipeline_result: Mapping[str, Any], replay: Mapping[str, Any] | None
) -> str | None:
    direct = pipeline_result.get("map_name")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    map_value = pipeline_result.get("map")
    if isinstance(map_value, Mapping):
        name = map_value.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if replay is not None:
        header = replay.get("header")
        if isinstance(header, Mapping):
            for key in ("map_name", "map"):
                name = header.get(key)
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return None


def _context_aliases(
    player_id: str, opponent_id: str, known_events: list[dict[str, Any]]
) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if player_id:
        aliases[player_id] = "player_01"
    if opponent_id and opponent_id != player_id:
        aliases[opponent_id] = "player_02"
    next_index = 3
    for event in known_events:
        participants = event.get("participant_ids")
        if not isinstance(participants, list):
            continue
        for participant in participants:
            raw = str(participant or "")
            if raw and raw not in aliases:
                aliases[raw] = f"player_{next_index:02d}"
                next_index += 1
    return aliases


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _positive_number(value: Any) -> bool:
    parsed = _number(value)
    return parsed is not None and parsed > 0


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
