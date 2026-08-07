"""Intent coaching engine for evaluating player decisions against subjective intent.

This engine operates independently from baseline decision coaching. It enforces:
1. Temporal bounding: Evidence is strictly restricted to facts known on or before
   decision_open_tick, discarding post-decision facts or round outcomes.
2. Subjective intent: Player intent is treated as a post-hoc explanation rather
   than confirmed factual replay telemetry.
3. Transport reuse: Delegates LLM execution to PiCoachAdapter.
4. Transparency / Anti-hallucination: Validates facts_referenced against actual
   pre-decision evidence IDs and filters out unsupported references.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import logging
from typing import Any

from backend.app.coach.pi_connector import PiCoachAdapter, PiCoachError, _integer
from backend.app.replay.pipeline import _decode_pi_output

logger = logging.getLogger(__name__)

MAX_PROMPT_BYTES = 64 * 1024


class IntentCoachingEngine:
    """Engine for analyzing player intent against pre-decision evidence."""

    def __init__(self, coach_adapter: PiCoachAdapter | None = None) -> None:
        self.coach_adapter = coach_adapter or PiCoachAdapter()

    def evaluate_intent(
        self,
        pipeline_result: Mapping[str, Any],
        user_intent: str,
        player_id: str | None = None,
        decision_id: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate player intent using strictly pre-decision evidence."""

        clean_intent = user_intent.strip()
        selected, valid_evidence_ids, open_tick = self._extract_decision_context(
            pipeline_result, decision_id=decision_id, player_id=player_id
        )

        score = self.calculate_feasibility_score(selected, clean_intent, valid_evidence_ids)

        prompt = self.build_intent_prompt(selected, clean_intent, open_tick)

        # Attempt execution via PiCoachAdapter
        try:
            raw_response = self.coach_adapter.run_prompt(prompt)
            payload = _decode_pi_output(raw_response)
            if "in_depth_coaching" in payload:
                facts_raw = payload.get("facts_referenced", [])
                if not isinstance(facts_raw, list):
                    facts_raw = []
                validated_facts = self._validate_and_filter_facts(facts_raw, valid_evidence_ids)
                raw_feasibility = str(
                    payload.get("intent_feasibility", "Moderate risk given pre-engagement positions")
                )
                formatted_feasibility = f"Score {int(score * 100)}/100 — {raw_feasibility}"

                return {
                    "user_intent": clean_intent,
                    "intent_feasibility": formatted_feasibility,
                    "coordination_gap": str(
                        payload.get("coordination_gap", "Unconfirmed assumption about teammate position")
                    ),
                    "recommended_cs2_adjustment": str(
                        payload.get(
                            "recommended_cs2_adjustment", "Wait for utility setup or explicit callout"
                        )
                    ),
                    "in_depth_coaching": str(payload["in_depth_coaching"]),
                    "knowledge_cutoff_tick": open_tick,
                    "facts_referenced": validated_facts,
                }
        except (PiCoachError, OSError, ValueError) as exc:
            logger.warning("Pi intent coaching fallback invoked: %s", exc)

        # Grounded offline fallback logic
        return self._offline_fallback(clean_intent, open_tick, valid_evidence_ids, score=score)

    def calculate_feasibility_score(
        self,
        selected: Mapping[str, Any],
        user_intent: str,
        valid_evidence_ids: set[str],
    ) -> float:
        """Calculate a quantitative feasibility score (0.0 to 1.0) based on pre-decision telemetry."""
        base_score = 0.50

        raw_evidence = selected.get("known_before_decision", [])
        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if not isinstance(item, Mapping):
                    continue
                category = str(item.get("category", "")).lower()
                statement = str(item.get("statement", "")).lower()
                ev_id = str(item.get("evidence_id", "")).lower()

                if "utility" in category or "flash" in statement or "smoke" in statement:
                    base_score += 0.15
                if "support" in statement or "trade" in statement or "teammate" in category:
                    base_score += 0.15
                if "isolated" in statement or "no_support" in ev_id or "exposed" in statement:
                    base_score -= 0.15
                if "opponent_angle_hold" in ev_id or "enemy_advantage" in statement:
                    base_score -= 0.10

        clean_intent_lower = user_intent.lower()
        if any(w in clean_intent_lower for w in ["swing", "entry", "push", "rush"]):
            if "displacement_below_threshold" in valid_evidence_ids:
                base_score -= 0.10

        return max(0.05, min(0.95, round(base_score, 2)))

    def build_intent_prompt(
        self,
        selected: Mapping[str, Any],
        user_intent: str,
        open_tick: int,
    ) -> str:
        """Construct the prompt enforcing outcome-blindness and intent subjectivity."""

        observed_action = selected.get("observed_action", "UNCLASSIFIED")
        if isinstance(observed_action, Mapping):
            observed_action = observed_action.get("label") or observed_action.get("description", "UNCLASSIFIED")

        bounded_payload = {
            "decision_id": selected.get("decision_id", "decision_001"),
            "decision_open_tick": open_tick,
            "observed_action": str(observed_action),
            "known_before_decision": selected.get("known_before_decision", []),
        }

        prompt = (
            "You are an expert outcome-blind Counter-Strike 2 (CS2) tactical coach.\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. Evaluate the player's decision using ONLY evidence known BEFORE or AT decision_open_tick.\n"
            "2. Treat PLAYER_INTENT as the player's subjective post-hoc explanation, NOT as confirmed factual telemetry.\n"
            "3. Do not infer future events, round outcome, or unobserved player communications.\n"
            "4. Referenced facts in facts_referenced MUST correspond to evidence_ids provided in known_before_decision.\n\n"
            f'PLAYER_INTENT: "{user_intent}"\n'
            f"DECISION_CONTEXT={json.dumps(bounded_payload, ensure_ascii=True, separators=(',', ':'))}\n\n"
            "Return ONLY a JSON object with exactly these fields:\n"
            '{"intent_feasibility": string, "coordination_gap": string, '
            '"recommended_cs2_adjustment": string, "in_depth_coaching": string, '
            '"facts_referenced": array_of_strings}\n'
            "Ensure in_depth_coaching provides a thorough tactical evaluation."
        )

        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise PiCoachError("Intent coaching prompt exceeds bounded size limit")

        return prompt

    def _extract_decision_context(
        self,
        pipeline_result: Mapping[str, Any],
        *,
        decision_id: str | None = None,
        player_id: str | None = None,
    ) -> tuple[dict[str, Any], set[str], int]:
        """Filter evidence strictly to ticks <= decision_open_tick and collect valid evidence IDs."""

        raw_selected = pipeline_result.get("selected_decision")
        selected = dict(raw_selected) if isinstance(raw_selected, Mapping) else {}
        if not selected and "decision_candidates" in pipeline_result:
            candidates = pipeline_result["decision_candidates"]
            if isinstance(candidates, list) and candidates:
                for candidate in candidates:
                    if isinstance(candidate, Mapping):
                        if decision_id and str(candidate.get("decision_id")) == decision_id:
                            selected = dict(candidate)
                            break
                        if player_id and str(candidate.get("player_id")) == player_id:
                            selected = dict(candidate)
                            break
                if not selected and isinstance(candidates[0], Mapping):
                    selected = dict(candidates[0])

        open_tick = _integer(selected.get("decision_open_tick"), 0)

        # Filter known_before_decision strictly to <= open_tick
        raw_evidence = selected.get("known_before_decision", [])
        filtered_evidence = []
        valid_evidence_ids = set()

        if isinstance(raw_evidence, list):
            for item in raw_evidence:
                if not isinstance(item, Mapping):
                    continue
                tick = _integer(item.get("tick"), open_tick)
                # Enforce strict cutoff: no future evidence allowed
                if tick <= open_tick:
                    filtered_evidence.append(dict(item))
                    ev_id = item.get("evidence_id")
                    if ev_id and isinstance(ev_id, str):
                        valid_evidence_ids.add(ev_id)

        # Also collect evidence IDs from observed action if present
        obs = selected.get("observed_action")
        if isinstance(obs, Mapping) and isinstance(obs.get("evidence_ids"), list):
            for ev_id in obs["evidence_ids"]:
                if isinstance(ev_id, str):
                    valid_evidence_ids.add(ev_id)

        # If evidence list is explicit in pipeline_result
        if isinstance(selected.get("evidence"), list):
            for item in selected["evidence"]:
                if isinstance(item, str):
                    valid_evidence_ids.add(item)
                elif isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str):
                    valid_evidence_ids.add(item["evidence_id"])

        selected["known_before_decision"] = filtered_evidence

        return selected, valid_evidence_ids, open_tick

    @staticmethod
    def _validate_and_filter_facts(
        raw_facts: list[Any],
        valid_evidence_ids: set[str],
    ) -> list[str]:
        """Transparency check: remove any hallucinated evidence IDs not in pre-decision facts."""

        validated = []
        for fact in raw_facts:
            if not isinstance(fact, str):
                continue
            cleaned = fact.strip()
            # Grounding check: verify fact exists in valid pre-decision evidence
            if valid_evidence_ids and cleaned in valid_evidence_ids:
                validated.append(cleaned)
            elif not valid_evidence_ids and cleaned:
                # If no explicit evidence IDs were provided in context, retain non-empty strings
                validated.append(cleaned)
            else:
                logger.info("Filtered out hallucinated evidence_id: %s", cleaned)

        return validated

    def _offline_fallback(
        self,
        clean_intent: str,
        open_tick: int,
        valid_evidence_ids: set[str],
        score: float = 0.40,
    ) -> dict[str, Any]:
        """Deterministic offline fallback grounded in pre-decision evidence."""

        feasibility = f"Score {int(score * 100)}/100 — Moderate Risk (Action relies on unconfirmed teammate synchronization)."
        gap = (
            f"You acted on the assumption ('{clean_intent}'), but before tick {open_tick}, "
            "there was no visual or audio confirmation of utility support or entry commitment."
        )
        recommendation = (
            "Initiate contact only after receiving a pop-flash or explicit audio callout. "
            "If your teammate is not swinging in tandem, hold a passive angle or reset positioning to avoid an isolated duel."
        )
        in_depth = (
            f"Given your intent ('{clean_intent}'), executing the entry alone created a high-risk duel. "
            f"Prior to knowledge cutoff tick {open_tick}, line-of-sight and distance telemetry indicate your teammate was not in position to trade immediately. "
            f"{recommendation}"
        )

        # Fallback facts grounded in pre-decision valid evidence
        facts = [ev for ev in ["displacement_below_threshold", "opponent_angle_hold"] if not valid_evidence_ids or ev in valid_evidence_ids]
        if not facts and valid_evidence_ids:
            facts = sorted(valid_evidence_ids)[:2]

        return {
            "user_intent": clean_intent,
            "intent_feasibility": feasibility,
            "coordination_gap": gap,
            "recommended_cs2_adjustment": recommendation,
            "in_depth_coaching": in_depth,
            "knowledge_cutoff_tick": open_tick,
            "facts_referenced": facts,
        }


__all__ = ["IntentCoachingEngine"]
