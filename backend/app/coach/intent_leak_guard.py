"""Fail-closed checks for internal labels in public intent-coaching prose.

The intent response contains both public natural-language fields and structured
metadata.  This module deliberately inspects only the natural-language fields:
structured values such as ``knowledge_cutoff_tick`` remain available to API
clients without allowing the model to repeat them in player-facing prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from collections.abc import Iterable, Mapping
from typing import Any


PUBLIC_COACHING_PROSE_FIELDS: tuple[str, ...] = (
    "intent_feasibility",
    "coordination_gap",
    "recommended_cs2_adjustment",
    "in_depth_coaching",
)

# Match the literal machine-facing names, case-insensitively.  Natural phrases
# such as "decision context" remain valid; only raw prompt/schema identifiers
# are forbidden.
FORBIDDEN_INTERNAL_TOKENS: tuple[str, ...] = (
    "DECISION_CONTEXT",
    "PLAYER_INTENT",
    "bounded_reaction_evidence",
    "known_before_decision",
    "facts_referenced",
    "evidence_id",
    "schema_version",
    "knowledge_cutoff_tick",
    "action_close_tick",
    "decision_open_tick",
    "contact_tick",
    "round_number",
    "player_id",
    "opponent_id",
    "decision_id",
    "event_id",
    "participant_ids",
    "event_category",
    "map_name",
    "available_utility",
    "known_events",
    "evidence_claims",
    "intent_assessment",
    "coordination_assessment",
    "recommended_adjustment",
    "intent_coach_input_v1",
)


class PublicProseViolationKind(str, Enum):
    """Stable categories callers can map to their public error contract."""

    INTERNAL_TOKEN = "internal_token"
    EXACT_TICK = "exact_tick"
    INVALID_TYPE = "invalid_type"


@dataclass(frozen=True, slots=True)
class PublicProseViolation:
    """Machine-readable description of a rejected prose field."""

    field_name: str
    kind: PublicProseViolationKind
    marker: str


class PublicCoachingProseError(ValueError):
    """Raised when provider prose would expose an internal implementation detail."""

    code = "unsafe_coaching_prose"

    def __init__(self, violation: PublicProseViolation) -> None:
        self.violation = violation
        super().__init__(
            f"Unsafe public coaching prose in {violation.field_name!r}: "
            f"{violation.kind.value} ({violation.marker!r})"
        )


_INTERNAL_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    + "|".join(re.escape(token) for token in FORBIDDEN_INTERNAL_TOKENS)
    + r")(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)

# Exact replay coordinates are forbidden in prose.  Numeric coaching guidance
# remains valid (for example, "35 health", "200 units", or "wait 2 seconds").
# A duration such as "within 160 ticks" is also not an exact coordinate and is
# therefore left alone.
_EXACT_TICK_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\btick\s*(?:(?:number|no\.?)\s*)?(?:was\s*)?(?:#\s*)?"
        r"(?:[-+:=]\s*)?\d+\b",
        flags=re.IGNORECASE,
    ),
    re.compile(r"\b(?:at\s+)?t\s*(?:[:=]\s*)?\d+\b", flags=re.IGNORECASE),
    re.compile(r"\b\d+(?:st|nd|rd|th)\s+tick\b", flags=re.IGNORECASE),
)
_RESIDUAL_PLAYER_ALIAS_RE = re.compile(
    r"(?<![A-Za-z0-9_])player_?\d{1,3}(?:_[A-Za-z0-9_]+)?(?![A-Za-z0-9_])",
    flags=re.IGNORECASE,
)


def validate_public_coaching_prose(
    prose: str,
    *,
    field_name: str = "coaching",
    forbidden_replay_coordinates: Iterable[int] = (),
) -> str:
    """Return *prose* unchanged, or raise for an internal-token/tick leak.

    Keeping this function non-mutating makes sanitization explicit: aliases
    should be translated before calling it, and anything still unsafe fails
    closed instead of being silently rewritten.
    """

    if not isinstance(prose, str):
        raise PublicCoachingProseError(
            PublicProseViolation(
                field_name=field_name,
                kind=PublicProseViolationKind.INVALID_TYPE,
                marker=type(prose).__name__,
            )
        )

    internal_match = _INTERNAL_TOKEN_RE.search(prose)
    if internal_match is not None:
        raise PublicCoachingProseError(
            PublicProseViolation(
                field_name=field_name,
                kind=PublicProseViolationKind.INTERNAL_TOKEN,
                marker=internal_match.group(0),
            )
        )

    alias_match = _RESIDUAL_PLAYER_ALIAS_RE.search(prose)
    if alias_match is not None:
        raise PublicCoachingProseError(
            PublicProseViolation(
                field_name=field_name,
                kind=PublicProseViolationKind.INTERNAL_TOKEN,
                marker=alias_match.group(0),
            )
        )

    for tick_pattern in _EXACT_TICK_RES:
        tick_match = tick_pattern.search(prose)
        if tick_match is not None:
            raise PublicCoachingProseError(
                PublicProseViolation(
                    field_name=field_name,
                    kind=PublicProseViolationKind.EXACT_TICK,
                    marker=tick_match.group(0),
                )
            )

    for coordinate in forbidden_replay_coordinates:
        if isinstance(coordinate, bool) or not isinstance(coordinate, int):
            continue
        coordinate_match = re.search(rf"(?<!\d){re.escape(str(coordinate))}(?!\d)", prose)
        if coordinate_match is not None:
            raise PublicCoachingProseError(
                PublicProseViolation(
                    field_name=field_name,
                    kind=PublicProseViolationKind.EXACT_TICK,
                    marker=coordinate_match.group(0),
                )
            )

    return prose


def validate_public_coaching_payload(
    payload: Mapping[str, Any],
    *,
    prose_fields: Iterable[str] = PUBLIC_COACHING_PROSE_FIELDS,
    forbidden_replay_coordinates: Iterable[int] = (),
) -> None:
    """Validate the configured public prose fields present in *payload*.

    Non-prose fields are intentionally ignored.  In particular,
    ``knowledge_cutoff_tick`` is valid structured metadata and is not checked.
    Missing fields remain the responsibility of the response schema validator.
    """

    for field_name in prose_fields:
        if field_name in payload:
            validate_public_coaching_prose(
                payload[field_name],
                field_name=field_name,
                forbidden_replay_coordinates=forbidden_replay_coordinates,
            )


__all__ = [
    "FORBIDDEN_INTERNAL_TOKENS",
    "PUBLIC_COACHING_PROSE_FIELDS",
    "PublicCoachingProseError",
    "PublicProseViolation",
    "PublicProseViolationKind",
    "validate_public_coaching_payload",
    "validate_public_coaching_prose",
]
