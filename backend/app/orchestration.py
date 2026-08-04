"""Day 1 fixture orchestration behind the frozen RE:DECIDE contracts."""

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
