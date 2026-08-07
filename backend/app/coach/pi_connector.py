"""Server-side coaching adapters for an already-prepared decision.

The replay pipeline remains authoritative. This adapter receives its selected,
outcome-blind result, builds a small anonymized prompt, and asks the configured
provider only for the explanation that ``merge_pi_output`` attaches to the API
response.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import httpx

MAX_PROMPT_BYTES = 64 * 1024
MAX_KNOWN_EVENTS_PER_DECISION = 24
DEFAULT_TIMEOUT_SECONDS = 180


class PiCoachError(RuntimeError):
    """Stable backend error for Pi configuration or response failures."""


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


def build_coach_prompt(pipeline_result: Mapping[str, Any]) -> str:
    """Build the bounded, outcome-blind prompt shared by every provider.

    Keeping this outside either provider adapter is intentional: switching
    between the local Pi process and an OpenAI-compatible HTTP endpoint must
    not change the evidence sent to the model.
    """

    payload = _model_payload(pipeline_result)
    multiple = isinstance(payload.get("decisions"), list) and len(payload["decisions"]) > 1
    response_instruction = (
        'Return ONLY one JSON object with an "analyses" array. Each item must contain exactly '
        'the string fields "decision_id" and "what_could_be_done_better".'
        if multiple
        else 'Return ONLY one JSON object with exactly these string fields: '
        '"decision_id" and "what_could_be_done_better".'
    )
    prompt = (
        "You are the explanation layer for an outcome-blind CS2 decision coach. "
        "Use only the supplied JSON evidence. Do not infer the round outcome, "
        "hidden communication, enemy intent, or events after action_close_tick. "
        f"{response_instruction} The coaching field must be one "
        "complete, concrete sentence naming the best available alternative and "
        "must not contain player aliases.\n\n"
        f"DECISION_PAYLOAD={json.dumps(payload, ensure_ascii=True, separators=(',', ':'))}"
    )
    if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
        raise PiCoachError("Pi coaching prompt exceeds the bounded payload size")
    return prompt


def validate_coach_response(payload: Mapping[str, Any], *, expected_decision_ids: set[str] | None = None) -> None:
    """Validate the provider-neutral coaching response contract."""

    if not isinstance(payload, Mapping):
        raise PiCoachError("Pi response did not contain a JSON object")
    if str(payload.get("decision_id") or "") not in (expected_decision_ids or {"decision_001"}):
        raise PiCoachError("Pi response did not reference the selected decision")
    coaching = payload.get("what_could_be_done_better")
    if not isinstance(coaching, str) or not coaching.strip():
        raise PiCoachError("Pi response did not contain coaching text")


def normalize_coach_response(value: str, *, expected_decision_ids: set[str] | None = None) -> str:
    """Parse and normalize a provider response to the API's strict JSON shape."""

    payload = _response_payload(value.strip())
    if isinstance(payload.get("analyses"), list):
        analyses = [item for item in payload["analyses"] if isinstance(item, Mapping)]
        if not analyses:
            raise PiCoachError("Pi response did not contain analyses")
        normalized = []
        for item in analyses:
            validate_coach_response(item, expected_decision_ids=expected_decision_ids)
            normalized.append({"decision_id": item["decision_id"], "what_could_be_done_better": item["what_could_be_done_better"]})
        return json.dumps({"analyses": normalized}, ensure_ascii=True)
    validate_coach_response(payload, expected_decision_ids=expected_decision_ids)
    return json.dumps(
        {
            "decision_id": payload["decision_id"],
            "what_could_be_done_better": payload["what_could_be_done_better"],
        },
        ensure_ascii=True,
    )


class HttpCoachAdapter:
    """Call an OpenAI-compatible model endpoint without spawning Node.js.

    Vercel's Python runtime should not depend on the local Node/Pi harness.
    The prompt and response validation intentionally stay identical to
    ``PiCoachAdapter`` so local and deployed coaching share one contract.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("HARNESS_MODEL_BASE_URL", "")).strip()
        self.api_key = (api_key or os.getenv("HARNESS_MODEL_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")).strip()
        self.model = (model or os.getenv("HARNESS_MODEL", "deepseek-v4-flash")).strip()
        self.timeout_seconds = timeout_seconds
        self._client = client

    def __call__(self, pipeline_result: Mapping[str, Any]) -> str:
        if not self.base_url:
            raise PiCoachError("HARNESS_MODEL_BASE_URL is required for HTTP coaching")
        if not self.api_key:
            raise PiCoachError(
                "HARNESS_MODEL_API_KEY or DEEPSEEK_API_KEY is required for HTTP coaching"
            )
        prompt = build_coach_prompt(pipeline_result)
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        close_client = self._client is None
        client = self._client or httpx.Client(timeout=httpx.Timeout(float(self.timeout_seconds)))
        try:
            response = client.post(endpoint, headers=headers, json=body)
            response.raise_for_status()
            response_body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PiCoachError("HTTP coaching provider failed") from exc
        finally:
            if close_client:
                client.close()
        try:
            content = response_body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise PiCoachError("HTTP coaching provider returned an invalid response") from exc
        if not isinstance(content, str):
            raise PiCoachError("HTTP coaching provider returned non-text content")
        return normalize_coach_response(content, expected_decision_ids=_expected_decision_ids(pipeline_result))


class PiCoachAdapter:
    """Call the Pi agent with one bounded selected-decision payload."""

    def __init__(
        self,
        *,
        repository_root: str | Path | None = None,
        node_executable: str | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        runner: ProcessRunner = subprocess.run,
    ) -> None:
        self.repository_root = (
            Path(repository_root)
            if repository_root is not None
            else Path(__file__).resolve().parents[3]
        )
        self.harness_root = self.repository_root / "agent-harness"
        self.node_executable = node_executable
        self.timeout_seconds = timeout_seconds
        self._runner = runner

    def __call__(self, pipeline_result: Mapping[str, Any]) -> str:
        prompt = build_coach_prompt(pipeline_result)
        executable = self._resolve_node()
        command = [
            executable,
            str(self.harness_root / "node_modules" / "tsx" / "dist" / "cli.mjs"),
            str(self.harness_root / "src" / "main.ts"),
            "--no-tools",
        ]
        try:
            completed = self._runner(
                command,
                cwd=self.harness_root,
                input=prompt,
                capture_output=True,
                env=self._process_environment(),
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PiCoachError("Pi coaching process timed out") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise PiCoachError("Pi coaching process could not be started") from exc
        if completed.returncode != 0:
            raise PiCoachError("Pi coaching process failed")
        return normalize_coach_response(completed.stdout, expected_decision_ids=_expected_decision_ids(pipeline_result))

    def _process_environment(self) -> dict[str, str]:
        """Inherit deployment values and point Pi at the repository dotenv.

        Pi's dotenv loader never overwrites an existing process variable, so
        deployment-provided credentials remain authoritative. The explicit
        path is needed because the subprocess runs from ``agent-harness/``.
        """

        environment = dict(os.environ)
        if not environment.get("HARNESS_ENV_FILE"):
            repository_env = self.repository_root / ".env"
            if repository_env.is_file():
                environment["HARNESS_ENV_FILE"] = str(repository_env.resolve())
        return environment

    def build_prompt(self, pipeline_result: Mapping[str, Any]) -> str:
        return build_coach_prompt(pipeline_result)

    def _resolve_node(self) -> str:
        if self.node_executable:
            return self.node_executable
        candidate = "node.exe" if sys.platform == "win32" else "node"
        resolved = shutil.which(candidate)
        if resolved is None:
            raise PiCoachError("Node.js is required to run the Pi coach adapter")
        if not (self.harness_root / "package.json").is_file():
            raise PiCoachError("agent-harness package is missing")
        if not (self.harness_root / "node_modules" / "tsx" / "dist" / "cli.mjs").is_file():
            raise PiCoachError("agent-harness dependencies are not installed")
        return resolved

    @staticmethod
    def _validate_response(payload: Mapping[str, Any]) -> None:
        validate_coach_response(payload)


def _model_payload(pipeline_result: Mapping[str, Any]) -> dict[str, Any]:
    selected_many = pipeline_result.get("selected_decisions")
    if isinstance(selected_many, list) and len(selected_many) > 1:
        rendered = []
        for item in selected_many:
            if not isinstance(item, Mapping):
                continue
            single = dict(pipeline_result)
            single.pop("selected_decisions", None)
            single["selected_decision"] = item
            rendered.append(_model_payload(single))
        if not rendered:
            raise PiCoachError("selected decision is missing from the pipeline result")
        return {
            "schema_version": "pi_coach_input_v1",
            "decisions": [
                {
                    "decision": {**item["decision"], "decision_id": f"decision_{index:03d}"},
                    "known_events": item["known_events"],
                    "team_probability_at_decision": item["team_probability_at_decision"],
                }
                for index, item in enumerate(rendered, start=1)
            ],
            "limitations": [
                "Voice communications and player intent are unavailable.",
                "The recommendation is a model inference, not a replay fact.",
            ],
        }
    selected = pipeline_result.get("selected_decision")
    if not isinstance(selected, Mapping):
        raise PiCoachError("selected decision is missing from the pipeline result")
    decision_open_tick = _integer(selected.get("decision_open_tick"), -1)
    action_close_tick = _integer(selected.get("action_close_tick"), -1)
    if decision_open_tick < 0 or action_close_tick < decision_open_tick:
        raise PiCoachError("selected decision has an invalid evidence window")

    player_id = str(selected.get("player_id") or "")
    opponent_id = str(selected.get("opponent_id") or "")
    aliases = {player_id: "player_01"}
    if opponent_id and opponent_id != player_id:
        aliases[opponent_id] = "player_02"

    decision = {
        "decision_id": "decision_001",
        "round_number": selected.get("round_number"),
        "player_id": "player_01",
        "side": selected.get("side"),
        "role": selected.get("role"),
        "event_category": selected.get("event_category"),
        "decision_open_tick": decision_open_tick,
        "contact_tick": selected.get("contact_tick"),
        "action_close_tick": action_close_tick,
        "opponent_id": aliases.get(opponent_id, "unknown"),
        "observed_action": _anonymize_value(selected.get("observed_action"), aliases),
        "observed_action_confidence": selected.get("observed_action_confidence"),
        "evidence": [
            _anonymize_value(item, aliases)
            for item in list(selected.get("evidence") or [])
        ],
    }

    selected_round = _integer(selected.get("round_number"), -1)
    events = []
    for event in pipeline_result.get("key_events", []):
        if not isinstance(event, Mapping):
            continue
        tick = _integer(event.get("tick"), -1)
        if tick < 0 or tick > action_close_tick:
            continue
        if (
            selected_round >= 0
            and _integer(event.get("round_number"), -1) != selected_round
        ):
            continue
        participants = [
            aliases[str(value)]
            for value in event.get("participant_ids", [])
            if str(value) in aliases
        ]
        if player_id and "player_01" not in participants:
            continue
        events.append(
            {
                "event_id": f"event_{len(events) + 1:03d}",
                "event_type": _anonymize_value(event.get("event_type"), aliases),
                "key_event_type": _anonymize_value(event.get("key_event_type"), aliases),
                "round_number": event.get("round_number"),
                "tick": tick,
                "participant_ids": participants,
                "is_coaching_anchor": bool(event.get("is_coaching_anchor")),
            }
        )

    # A decision only needs the recent, outcome-blind context from its own
    # round.  Repeating every earlier match event for each selected decision
    # made full manual-demo prompts grow quadratically and exceed the 64 KiB
    # provider boundary.  Keep the closest events when a single round is noisy.
    events = events[-MAX_KNOWN_EVENTS_PER_DECISION:]

    probability = _probability_at_decision(pipeline_result, decision_open_tick)
    return {
        "schema_version": "pi_coach_input_v1",
        "decision": decision,
        "known_events": events,
        "team_probability_at_decision": probability,
        "limitations": [
            "Voice communications and player intent are unavailable.",
            "The recommendation is a model inference, not a replay fact.",
        ],
    }


def _probability_at_decision(
    pipeline_result: Mapping[str, Any], decision_tick: int
) -> dict[str, Any] | None:
    estimator = pipeline_result.get("win_estimator")
    if not isinstance(estimator, Mapping):
        return None
    timeline = [
        row
        for row in estimator.get("timeline", [])
        if isinstance(row, Mapping) and _integer(row.get("tick"), -1) <= decision_tick
    ]
    if not timeline:
        return None
    row = max(timeline, key=lambda item: _integer(item.get("tick"), -1))
    return {
        "tick": row.get("tick"),
        "ct_probability": row.get("ct_probability"),
        "t_probability": row.get("t_probability"),
        "uncertainty": row.get("uncertainty"),
    }


def _expected_decision_ids(pipeline_result: Mapping[str, Any]) -> set[str]:
    selected = pipeline_result.get("selected_decisions")
    if isinstance(selected, list) and selected:
        return {f"decision_{index:03d}" for index, _ in enumerate(selected, start=1)}
    return {"decision_001"}


def _anonymize_value(value: Any, aliases: Mapping[str, str]) -> Any:
    """Replace raw player identifiers in model-visible free-form values."""

    if not aliases:
        return value
    if isinstance(value, str):
        result = value
        for raw, alias in aliases.items():
            if raw:
                result = result.replace(raw, alias)
        return result
    if isinstance(value, list):
        return [_anonymize_value(item, aliases) for item in value]
    if isinstance(value, tuple):
        return tuple(_anonymize_value(item, aliases) for item in value)
    if isinstance(value, Mapping):
        return {
            _anonymize_value(key, aliases): _anonymize_value(item, aliases)
            for key, item in value.items()
        }
    return value


def _first_json_object(value: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise PiCoachError("Pi response did not contain a JSON object")


def _response_payload(value: str) -> dict[str, Any]:
    """Decode strict JSON or Pi's narrow unquoted-object rendering.

    Some OpenAI-compatible providers render a requested JSON object without
    quoting its keys or string values. Accept only the two expected fields in
    the requested order, then normalize them back to strict JSON before the
    replay pipeline sees the response.
    """

    try:
        return _first_json_object(value)
    except PiCoachError as strict_error:
        start = value.find("{")
        end = value.rfind("}")
        if start < 0 or end <= start:
            raise strict_error
        candidate = value[start : end + 1]
        match = re.fullmatch(
            r"\{\s*['\"]?decision_id['\"]?\s*:\s*['\"]?"
            r"(?P<decision>decision_001)['\"]?\s*,\s*"
            r"['\"]?what_could_be_done_better['\"]?\s*:\s*"
            r"(?P<coaching>.*?)\s*\}",
            candidate,
            flags=re.DOTALL,
        )
        if match is None:
            raise strict_error
        coaching = match.group("coaching").strip()
        if len(coaching) >= 2 and coaching[0] == coaching[-1] and coaching[0] in {"'", '"'}:
            coaching = coaching[1:-1].strip()
        return {
            "decision_id": match.group("decision"),
            "what_could_be_done_better": coaching,
        }


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "HttpCoachAdapter",
    "PiCoachAdapter",
    "PiCoachError",
    "build_coach_prompt",
    "normalize_coach_response",
    "validate_coach_response",
]
