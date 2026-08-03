"""Deterministic ranking of caller-supplied legal tactical alternatives.

Replay data is observational, so this module never invents actions or labels a
counterfactual as proven.  A simulator/map adapter must provide legal
candidate actions and their model estimates; this layer only applies stable
support and outcome ordering.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def rank_candidate_actions(
    candidates: Iterable[dict[str, Any]],
    *,
    min_support: int = 5,
    max_entropy: float = 0.95,
) -> list[dict[str, Any]]:
    """Return legal candidates in a deterministic, support-aware order.

    Candidates should contain ``action`` and may contain ``death_probability``,
    ``round_value_delta``, ``sample_count``, and ``entropy``.  Unsupported or
    high-entropy estimates remain visible but are ranked after supported ones.
    """

    if min_support < 0:
        raise ValueError("min_support cannot be negative")
    if not 0 <= max_entropy <= 1:
        raise ValueError("max_entropy must be between 0 and 1")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise TypeError("each candidate must be an object")
        action = str(candidate.get("action") or "").strip()
        if not action or action in seen:
            if action:
                raise ValueError(f"duplicate or empty legal action: {action!r}")
            raise ValueError("candidate action must be non-empty")
        seen.add(action)
        support = int(_number(candidate.get("sample_count"), 0.0) or 0)
        entropy = _number(candidate.get("entropy"), 1.0)
        death = _number(candidate.get("death_probability"), 0.5)
        value_delta = _number(candidate.get("round_value_delta"), 0.0)
        confidence = _number(candidate.get("confidence"), support / (support + 10.0))
        supported = support >= min_support and (entropy is None or entropy <= max_entropy)
        item = dict(candidate)
        item.update(
            {
                "action": action,
                "sample_count": support,
                "death_probability": death,
                "round_value_delta": value_delta,
                "confidence": confidence,
                "supported": supported,
                "estimate_type": "observational_counterfactual_estimate",
            }
        )
        output.append(item)
    output.sort(
        key=lambda item: (
            not bool(item["supported"]),
            -float(item["round_value_delta"]),
            float(item["death_probability"]),
            -float(item["confidence"]),
            item["action"],
        )
    )
    for rank, item in enumerate(output, start=1):
        item["rank"] = rank
    return output


__all__ = ["rank_candidate_actions"]
