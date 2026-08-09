"""Strict claim-to-evidence validation for intent coaching.

The language model may select which authoritative evidence items support its
coaching fields, but it is not trusted to restate those facts.  Public factual
text is rendered only from server-owned evidence statements.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


EvidenceClaimTarget = Literal[
    "intent_feasibility",
    "coordination_gap",
    "recommended_cs2_adjustment",
    "in_depth_coaching",
]


class IntentClaimValidationError(ValueError):
    """Provider claim mappings or authoritative evidence are unsafe."""


class ProviderEvidenceClaim(BaseModel):
    """One provider-selected link from a coaching field to one evidence item.

    Deliberately no free-text claim field exists.  ``extra='forbid'`` ensures a
    provider cannot smuggle factual prose into the deterministic renderer.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_id: str = Field(min_length=1)
    supports: EvidenceClaimTarget

    @field_validator("evidence_id")
    @classmethod
    def evidence_id_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("evidence_id cannot be blank")
        return cleaned


class ProviderEvidenceClaims(BaseModel):
    """Provider field that can be embedded in the intent response schema."""

    model_config = ConfigDict(extra="forbid", strict=True)

    evidence_claims: list[ProviderEvidenceClaim] = Field(min_length=1)

    @field_validator("evidence_claims")
    @classmethod
    def claim_targets_must_be_unique(
        cls, value: list[ProviderEvidenceClaim]
    ) -> list[ProviderEvidenceClaim]:
        pairs = [(claim.evidence_id, claim.supports) for claim in value]
        if len(pairs) != len(set(pairs)):
            raise ValueError(
                "evidence_claims cannot repeat an evidence-ID/target pair"
            )
        return value


class GroundedEvidenceClaim(BaseModel):
    """Validated internal claim containing a server-authored statement."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    evidence_id: str
    supports: EvidenceClaimTarget
    statement: str


_PLAYER_ALIAS_RE = re.compile(r"\bplayer_(\d+)\b", re.IGNORECASE)
_STEAM_ID_RE = re.compile(r"(?<!\d)\d{15,20}(?!\d)")
_INTERNAL_LABEL_RE = re.compile(
    r"\b(?:STEAM_PLAYER_ID|DECISION_CONTEXT|PLAYER_INTENT|EVIDENCE_ID)\b",
    re.IGNORECASE,
)
_EVIDENCE_ID_RE = re.compile(
    r"\b(?:decision|event|telemetry):[A-Za-z0-9_.:-]+\b", re.IGNORECASE
)


def validate_evidence_claims(
    provider_claims: Any,
    authoritative_evidence: Sequence[Mapping[str, Any]] | Mapping[str, str],
) -> list[GroundedEvidenceClaim]:
    """Validate provider mappings and attach server-authored statements.

    ``provider_claims`` is the value of the provider's ``evidence_claims``
    field.  The returned claims are ordered by ``authoritative_evidence``, not
    by provider output, so prompt ordering cannot alter the public summary.
    """

    try:
        parsed = ProviderEvidenceClaims.model_validate(
            {"evidence_claims": provider_claims}
        )
    except ValidationError as exc:
        raise IntentClaimValidationError(
            "provider evidence_claims did not satisfy the strict schema"
        ) from exc

    evidence_order, statements = _authoritative_statements(authoritative_evidence)
    claims_by_id: dict[str, list[ProviderEvidenceClaim]] = {}
    for claim in parsed.evidence_claims:
        claims_by_id.setdefault(claim.evidence_id, []).append(claim)
    unknown_ids = set(claims_by_id).difference(statements)
    if unknown_ids:
        raise IntentClaimValidationError(
            "provider evidence_claims referenced unknown evidence IDs"
        )

    return [
        GroundedEvidenceClaim(
            evidence_id=evidence_id,
            supports=claim.supports,
            statement=statements[evidence_id],
        )
        for evidence_id in evidence_order
        for claim in claims_by_id.get(evidence_id, [])
    ]


def render_public_evidence_summary(
    claims: Iterable[GroundedEvidenceClaim],
    *,
    max_items: int = 3,
) -> str:
    """Render a concise factual summary without exposing internal identifiers."""

    if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
        raise IntentClaimValidationError("max_items must be a positive integer")

    statements: list[str] = []
    rendered_ids: set[str] = set()
    for claim in claims:
        if len(statements) >= max_items:
            break
        if claim.evidence_id in rendered_ids:
            continue
        public_statement = _public_statement(claim.statement)
        if public_statement:
            statements.append(_sentence(public_statement))
            rendered_ids.add(claim.evidence_id)

    if not statements:
        raise IntentClaimValidationError(
            "at least one grounded evidence statement is required"
        )
    return "Replay evidence: " + " ".join(statements)


def build_public_evidence_summary(
    provider_claims: Any,
    authoritative_evidence: Sequence[Mapping[str, Any]] | Mapping[str, str],
    *,
    max_items: int = 3,
) -> str:
    """Validate mappings and render their server-owned public fact summary."""

    claims = validate_evidence_claims(provider_claims, authoritative_evidence)
    return render_public_evidence_summary(claims, max_items=max_items)


def _authoritative_statements(
    evidence: Sequence[Mapping[str, Any]] | Mapping[str, str],
) -> tuple[list[str], dict[str, str]]:
    if isinstance(evidence, Mapping):
        entries = [
            {"evidence_id": evidence_id, "statement": statement}
            for evidence_id, statement in evidence.items()
        ]
    else:
        entries = list(evidence)

    order: list[str] = []
    statements: dict[str, str] = {}
    for item in entries:
        if not isinstance(item, Mapping):
            raise IntentClaimValidationError(
                "authoritative evidence entries must be mappings"
            )
        evidence_id = str(item.get("evidence_id") or "").strip()
        statement = str(item.get("statement") or "").strip()
        if not evidence_id or not statement:
            raise IntentClaimValidationError(
                "authoritative evidence requires nonblank evidence_id and statement"
            )
        if evidence_id in statements:
            raise IntentClaimValidationError(
                "authoritative evidence contains duplicate evidence IDs"
            )
        order.append(evidence_id)
        statements[evidence_id] = statement
    return order, statements


def _public_statement(value: str) -> str:
    """Remove internal labels from a trusted server statement before display."""

    cleaned = value.strip()
    # Replay coordinates remain available as structured response metadata, not
    # as player-facing prose. Replace common exact-coordinate phrasings before
    # the final fail-closed prose guard checks the rendered response.
    cleaned = re.sub(
        r"\bat\s+tick\s*(?:was\s*)?(?:#\s*)?(?:[-+:=]\s*)?\d+\b",
        "at the decision moment",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\btick\s*(?:was\s*)?(?:#\s*)?(?:[-+:=]\s*)?\d+\b",
        "the decision moment",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:at\s+)?t\s*(?:[:=]\s*)?\d+\b",
        "at the decision moment",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b\d+(?:st|nd|rd|th)\s+tick\b",
        "the decision moment",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\bPLAYER_INTENT\b", "your stated intent", cleaned)
    cleaned = re.sub(r"\bDECISION_CONTEXT\b", "the decision context", cleaned)
    cleaned = re.sub(
        r"\bSTEAM_PLAYER_ID\s+\d{15,20}\b",
        "a player",
        cleaned,
        flags=re.IGNORECASE,
    )

    def replace_player(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if number == 1:
            return "you"
        if number == 2:
            return "the opponent"
        return "another player"

    cleaned = _PLAYER_ALIAS_RE.sub(replace_player, cleaned)
    cleaned = _STEAM_ID_RE.sub("a player", cleaned)
    cleaned = _EVIDENCE_ID_RE.sub("the recorded evidence", cleaned)
    cleaned = _INTERNAL_LABEL_RE.sub("the recorded value", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _sentence(value: str) -> str:
    sentence = value.rstrip()
    if sentence[-1] not in ".!?":
        sentence += "."
    return sentence


__all__ = [
    "EvidenceClaimTarget",
    "GroundedEvidenceClaim",
    "IntentClaimValidationError",
    "ProviderEvidenceClaim",
    "ProviderEvidenceClaims",
    "build_public_evidence_summary",
    "render_public_evidence_summary",
    "validate_evidence_claims",
]
