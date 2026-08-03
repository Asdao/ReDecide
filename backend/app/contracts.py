"""Frozen version 1.0 contracts shared across RE:DECIDE components.

Person 2 produces :class:`DecisionPacket`, Person 4 produces
:class:`IntentInput`, and Person 3 produces :class:`DecisionCard`. Changes to
field names, enum values, or cutoff semantics require coordination through
Person 1 and a deliberate schema migration.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class ContractModel(BaseModel):
    """Base configuration for strict API-boundary objects."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class DecisionType(StrEnum):
    POST_CONTACT_RESET = "POST_CONTACT_RESET"


class ObservedActionLabel(StrEnum):
    IMMEDIATE_REENGAGE = "IMMEDIATE_REENGAGE"
    RESET_REPOSITION = "RESET_REPOSITION"
    RELOAD_EXPOSED = "RELOAD_EXPOSED"
    HOLD_FOR_SUPPORT = "HOLD_FOR_SUPPORT"
    UNCLASSIFIED = "UNCLASSIFIED"


class IntentTag(StrEnum):
    TAKE_DUEL = "TAKE_DUEL"
    CREATE_SPACE = "CREATE_SPACE"
    HELP_TEAMMATE = "HELP_TEAMMATE"
    ESCAPE = "ESCAPE"
    UNKNOWN = "UNKNOWN"


class Verdict(StrEnum):
    GOOD_DECISION = "GOOD_DECISION"
    REASONABLE_BUT_RISKY = "REASONABLE_BUT_RISKY"
    POOR_DECISION = "POOR_DECISION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceItem(ContractModel):
    evidence_id: str = Field(min_length=1)
    tick: int = Field(ge=0)
    category: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    value: JsonValue
    source: str = Field(min_length=1)


class ObservedAction(ContractModel):
    label: ObservedActionLabel
    description: str = Field(min_length=1)
    evidence_ids: list[str]

    @model_validator(mode="after")
    def evidence_references_are_unique(self) -> "ObservedAction":
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("observed_action evidence_ids must be unique")
        if any(not evidence_id.strip() for evidence_id in self.evidence_ids):
            raise ValueError("observed_action evidence_ids cannot be blank")
        return self


class DataQuality(ContractModel):
    score: float = Field(ge=0.0, le=1.0)
    warnings: list[str]


class DecisionPacket(ContractModel):
    """Outcome-blind facts emitted by the replay pipeline."""

    schema_version: str = Field(pattern=r"^1\.0$")
    decision_id: str = Field(min_length=1)
    match_id: str = Field(min_length=1)
    map: str = Field(min_length=1)
    round_number: int = Field(ge=1)
    player: str = Field(min_length=1)
    decision_type: DecisionType
    decision_open_tick: int = Field(ge=0)
    decision_open_seconds: float = Field(ge=0.0)
    action_close_tick: int = Field(ge=0)
    known_before_decision: list[EvidenceItem]
    observed_action: ObservedAction
    unknowns: list[str]
    data_quality: DataQuality

    @model_validator(mode="after")
    def enforce_knowledge_boundaries(self) -> "DecisionPacket":
        if self.action_close_tick < self.decision_open_tick:
            raise ValueError(
                "action_close_tick must be at or after decision_open_tick"
            )

        future_evidence = [
            item.evidence_id
            for item in self.known_before_decision
            if item.tick > self.decision_open_tick
        ]
        if future_evidence:
            raise ValueError(
                "known_before_decision contains evidence after "
                f"decision_open_tick: {future_evidence}"
            )

        evidence_ids = [item.evidence_id for item in self.known_before_decision]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("known_before_decision evidence_ids must be unique")
        return self

    def available_evidence_ids(self) -> set[str]:
        """Return all evidence references carried by the packet."""

        known_ids = {item.evidence_id for item in self.known_before_decision}
        return known_ids | set(self.observed_action.evidence_ids)


class IntentInput(ContractModel):
    tag: IntentTag
    text: str | None = None


class DecisionOption(ContractModel):
    action: str = Field(min_length=1)
    tradeoff: str = Field(min_length=1)
    when_best: str = Field(min_length=1)


class NextMatchQuest(ContractModel):
    cue: str = Field(min_length=1)
    action: str = Field(min_length=1)
    success_check: str = Field(min_length=1)


class DecisionChecks(ContractModel):
    unsupported_evidence_ids: list[str]
    future_information_detected: bool
    contradiction_detected: bool


class DecisionCard(ContractModel):
    """Evidence-linked coaching result returned to the frontend."""

    schema_version: str = Field(pattern=r"^1\.0$")
    decision_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    verdict: Verdict
    confidence: float = Field(ge=0.0, le=1.0)
    assessment: str = Field(min_length=1)
    player_intent_summary: str = Field(min_length=1)
    facts_used: list[str]
    options: list[DecisionOption]
    recommended_action: str = Field(min_length=1)
    why: str = Field(min_length=1)
    execution_note: str | None = None
    next_match_quest: NextMatchQuest
    limitations: list[str]
    checks: DecisionChecks

    @model_validator(mode="after")
    def fact_references_are_unique(self) -> "DecisionCard":
        if len(self.facts_used) != len(set(self.facts_used)):
            raise ValueError("facts_used evidence IDs must be unique")
        if any(not evidence_id.strip() for evidence_id in self.facts_used):
            raise ValueError("facts_used evidence IDs cannot be blank")
        return self


class AnalyzeJsonRequest(ContractModel):
    """API envelope; the three nested product contracts remain unchanged."""

    decision_packet: DecisionPacket
    intent: IntentInput
