"""Deterministic ranking of caller-supplied legal tactical alternatives.

Replay data is observational, so this module never invents actions or labels a
counterfactual as proven.  A simulator/map adapter must provide legal
candidate actions and their model estimates; this layer only applies stable
support and outcome ordering.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from Noah.training.bayesian_decisions import (
    BetaPosterior,
    compare_posteriors,
    posterior_from_probability,
)


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


@dataclass(frozen=True, slots=True)
class ProbabilityLabelThresholds:
    """Conservative thresholds for probability-based decision labels.

    Candidate scores are observational/simulator estimates.  These thresholds
    therefore require both a meaningful expected gap and high probability that
    the gap is real before emitting ``good`` or ``bad``; otherwise the caller
    should abstain.
    """

    min_support: int = 5
    probability_of_improvement: float = 0.8
    expected_regret: float = 0.05
    credible_level: float = 0.9
    max_interval_width: float = 0.8
    posterior_samples: int = 5000
    seed: int = 7

    def __post_init__(self) -> None:
        if self.min_support < 0:
            raise ValueError("min_support cannot be negative")
        if not 0.5 < self.probability_of_improvement < 1.0:
            raise ValueError("probability_of_improvement must be between 0.5 and 1")
        if self.expected_regret < 0:
            raise ValueError("expected_regret cannot be negative")
        if not 0 < self.credible_level < 1:
            raise ValueError("credible_level must be between zero and one")
        if not 0 < self.max_interval_width <= 1:
            raise ValueError("max_interval_width must be between zero and one")
        if self.posterior_samples <= 0:
            raise ValueError("posterior_samples must be positive")

    def to_dict(self) -> dict[str, float | int]:
        return {
            "min_support": self.min_support,
            "probability_of_improvement": self.probability_of_improvement,
            "expected_regret": self.expected_regret,
            "credible_level": self.credible_level,
            "max_interval_width": self.max_interval_width,
            "posterior_samples": self.posterior_samples,
            "seed": self.seed,
        }


PROBABILITY_LABEL_SCHEMA_VERSION = "probability_labels_v1"


def _horner(coefficients: tuple[float, ...], value: float) -> float:
    result = coefficients[0]
    for coefficient in coefficients[1:]:
        result = result * value + coefficient
    return result


def _normal_quantile(probability: float) -> float:
    """Inverse standard-normal CDF using a dependency-free approximation."""

    # Peter John Acklam's rational approximation, adequate for confidence
    # thresholds used in reports and deterministic across supported runtimes.
    if not 0 < probability < 1:
        raise ValueError("normal quantile requires a probability in (0, 1)")
    a = (-39.6968302866538, 220.946098424521, -275.928510446969, 138.357751867269, -30.6647980661472, 2.50662827745924)
    b = (-54.4760987982241, 161.585836858041, -155.698979859887, 66.8013118877197, -13.2806815528857)
    c = (-0.00778489400243029, -0.322396458041136, -2.40075827716184, -2.54973253934373, 4.37466414146497, 2.93816398269878)
    d = (0.00778469570904146, 0.32246712907004, 2.445134137143, 3.75440866190742)
    lower, upper = 0.02425, 1 - 0.02425
    if probability < lower:
        q = math.sqrt(-2 * math.log(probability))
        return _horner(c, q) / (_horner(d, q) * q + 1)
    if probability > upper:
        q = math.sqrt(-2 * math.log(1 - probability))
        return -_horner(c, q) / (_horner(d, q) * q + 1)
    q = probability - 0.5
    r = q * q
    return _horner(a, r) * q / (_horner(b, r) * r + 1)


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _candidate_probability(candidate: dict[str, Any]) -> float:
    value = _number(candidate.get("candidate_success_probability"), None)
    if value is None:
        value = _number(candidate.get("round_value_delta"), 0.5)
    return min(1.0, max(0.0, float(value)))


def _candidate_posterior(candidate: dict[str, Any]) -> BetaPosterior:
    successes = _number(candidate.get("posterior_successes"), None)
    failures = _number(candidate.get("posterior_failures"), None)
    if successes is not None and failures is not None and successes >= 0 and failures >= 0:
        return BetaPosterior(successes, failures)
    support = max(0.0, _number(candidate.get("sample_count"), 0.0) or 0.0)
    return posterior_from_probability(_candidate_probability(candidate), support)


def _has_outcome_evidence(candidate: dict[str, Any]) -> bool:
    """Return whether a candidate carries labelled outcome counts.

    ``sample_count`` is action-observation support, not a success/failure
    sample size.  It is therefore never sufficient for a directional
    probability comparison on its own.
    """

    if candidate.get("outcome_evidence") is True:
        return True
    successes = _number(candidate.get("posterior_successes"), None)
    failures = _number(candidate.get("posterior_failures"), None)
    return successes is not None and failures is not None and successes + failures > 0


def _has_outcome_variance(
    candidate: dict[str, Any],
    peer: dict[str, Any],
) -> bool:
    explicit = candidate.get("outcome_variance")
    if isinstance(explicit, bool):
        return explicit
    explicit_peer = peer.get("outcome_variance")
    if isinstance(explicit_peer, bool):
        return explicit_peer
    # A direct report with raw posterior counts can be compared without the
    # harness' shared variance annotation, provided the labelled means differ.
    values: list[float] = []
    for row in (candidate, peer):
        successes = _number(row.get("posterior_successes"), None)
        failures = _number(row.get("posterior_failures"), None)
        if successes is None or failures is None or successes + failures <= 0:
            return False
        values.append((successes + 1.0) / (successes + failures + 2.0))
    return max(values) - min(values) > 1e-9


def _candidate_interval(candidate: dict[str, Any], *, level: float) -> dict[str, Any]:
    probability = _candidate_probability(candidate)
    successes = _number(candidate.get("posterior_successes"), None)
    failures = _number(candidate.get("posterior_failures"), None)
    if successes is not None and failures is not None and successes >= 0 and failures >= 0:
        observations = successes + failures
        posterior_mean = (successes + 1.0) / (observations + 2.0)
    else:
        support = max(0.0, _number(candidate.get("sample_count"), 0.0) or 0.0)
        observations = support
        # Action support is not necessarily outcome-label support. Treating it
        # as an effective sample count gives a conservative interval while
        # making that limitation explicit in the method field.
        posterior_mean = probability
    effective_n = observations + 2.0
    standard_error = math.sqrt(max(0.0, posterior_mean * (1.0 - posterior_mean) / effective_n))
    z = _normal_quantile(0.5 + level / 2.0)
    lower = max(0.0, posterior_mean - z * standard_error)
    upper = min(1.0, posterior_mean + z * standard_error)
    return {
        "level": level,
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "mean": posterior_mean,
        "method": "beta_normal_approximation" if successes is not None and failures is not None else "support_proxy_normal_approximation",
        "observations": int(observations),
    }


def annotate_probability_labels(
    report: dict[str, Any],
    *,
    thresholds: ProbabilityLabelThresholds | None = None,
) -> dict[str, Any]:
    """Add probability-based labels without removing legacy classifications.

    The existing ``decision_class`` remains untouched for API compatibility.
    New ``probability_decision_class`` fields are ``good``, ``bad``,
    ``neutral``, or ``insufficient_evidence``.  Every abstention includes a
    machine-readable reason and the thresholds used.
    """

    settings = thresholds or ProbabilityLabelThresholds()
    output = dict(report)
    output["probability_label_schema_version"] = PROBABILITY_LABEL_SCHEMA_VERSION
    moments: list[dict[str, Any]] = []
    label_counts: dict[str, int] = {}
    for original in report.get("moments") or []:
        item = dict(original)
        candidates = [dict(candidate) for candidate in item.get("candidate_actions") or [] if isinstance(candidate, dict)]
        for candidate in candidates:
            candidate["credible_interval"] = _candidate_interval(candidate, level=settings.credible_level)
        item["candidate_actions"] = candidates
        best = item.get("best_estimated_alternative")
        observed = item.get("observed_action")
        best = best if isinstance(best, dict) else None
        observed = observed if isinstance(observed, dict) else None
        best = dict(best) if best is not None else None
        observed = dict(observed) if observed is not None else None
        if best is not None:
            best["credible_interval"] = _candidate_interval(best, level=settings.credible_level)
            item["best_estimated_alternative"] = best
        if observed is not None:
            observed["credible_interval"] = _candidate_interval(observed, level=settings.credible_level)
            item["observed_action"] = observed
        abstain_reason: str | None = None
        probability_of_improvement: float | None = None
        expected_regret: float | None = None
        expected_regret_after_margin: float | None = None
        regret_delta: float | None = None
        posterior_comparison: dict[str, Any] | None = None
        label = "insufficient_evidence"
        observed_interval = _candidate_interval(observed, level=settings.credible_level) if observed else None
        best_interval = _candidate_interval(best, level=settings.credible_level) if best else None
        if best is None or observed is None:
            abstain_reason = "missing_observed_or_candidate_action"
        elif int(best.get("sample_count") or 0) < settings.min_support or int(observed.get("sample_count") or 0) < settings.min_support:
            abstain_reason = "support_below_threshold"
        elif not _has_outcome_evidence(best) or not _has_outcome_evidence(observed):
            abstain_reason = "outcome_support_missing"
        elif not _has_outcome_variance(best, observed):
            abstain_reason = "no_counterfactual_outcome_variance"
        elif best.get("supported") is False or observed.get("supported") is False:
            abstain_reason = "candidate_marked_unsupported"
        else:
            best_probability = _candidate_probability(best)
            observed_probability = _candidate_probability(observed)
            regret_delta = best_probability - observed_probability
            interval_too_wide = any(
                float(interval["width"]) > settings.max_interval_width
                for interval in (best_interval, observed_interval)
                if interval is not None
            )
            if interval_too_wide:
                abstain_reason = "credible_interval_too_wide"
            elif best.get("action") == observed.get("action"):
                # The observed action is already the ranked best action. There
                # is no distinct counterfactual to compare against.
                probability_of_improvement = 0.0
                expected_regret = 0.0
                expected_regret_after_margin = 0.0
                label = "good"
            else:
                posterior_comparison = compare_posteriors(
                    _candidate_posterior(observed),
                    _candidate_posterior(best),
                    epsilon=settings.expected_regret,
                    credible_level=settings.credible_level,
                    samples=settings.posterior_samples,
                    seed=settings.seed,
                )
                probability_of_improvement = float(
                    posterior_comparison["probability_alternative_beats_by_epsilon"]
                )
                expected_regret = float(posterior_comparison["expected_regret"])
                expected_regret_after_margin = float(
                    posterior_comparison["expected_regret_after_epsilon"]
                )
                regret_delta = float(posterior_comparison["expected_difference"])
                if (
                    probability_of_improvement >= settings.probability_of_improvement
                    and expected_regret_after_margin >= settings.expected_regret
                ):
                    label = "bad"
                elif (
                    probability_of_improvement <= 1.0 - settings.probability_of_improvement
                    and expected_regret_after_margin < settings.expected_regret
                ):
                    label = "good"
                else:
                    label = "neutral"
                    abstain_reason = (
                        "improvement_probability_below_threshold"
                        if probability_of_improvement < settings.probability_of_improvement
                        else "expected_gap_below_threshold"
                    )
        item.update(
            {
                "probability_decision_class": label,
                "probability_of_improvement": probability_of_improvement,
                "expected_regret": expected_regret,
                "expected_regret_after_margin": expected_regret_after_margin,
                "regret_delta": regret_delta,
                "posterior_comparison": posterior_comparison,
                "credible_intervals": {
                    "observed_action": observed_interval,
                    "best_estimated_alternative": best_interval,
                },
                "probability_abstention": {
                    "abstained": label == "insufficient_evidence",
                    "reason": abstain_reason,
                    "thresholds": settings.to_dict(),
                },
            }
        )
        moments.append(item)
        label_counts[label] = label_counts.get(label, 0) + 1
    output["moments"] = moments
    config = dict(output.get("config") or {})
    config["probability_thresholds"] = settings.to_dict()
    output["config"] = config
    summary = dict(output.get("summary") or {})
    summary["probability_decision_classes"] = dict(sorted(label_counts.items()))
    summary["probability_labels_are_thresholded_estimates"] = True
    output["summary"] = summary
    return output


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
        support_reason = None
        if support < min_support:
            support_reason = "support_below_threshold"
        elif entropy is not None and entropy > max_entropy:
            support_reason = "high_entropy"
        item = dict(candidate)
        estimate_type = str(
            item.get("estimate_type") or "observational_counterfactual_estimate"
        )
        item.update(
            {
                "action": action,
                "sample_count": support,
                "death_probability": death,
                "round_value_delta": value_delta,
                "confidence": confidence,
                "supported": supported,
                "support_reason": support_reason,
                "estimate_type": estimate_type,
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


__all__ = [
    "PROBABILITY_LABEL_SCHEMA_VERSION",
    "ProbabilityLabelThresholds",
    "annotate_probability_labels",
    "rank_candidate_actions",
]
