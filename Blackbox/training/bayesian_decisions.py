"""Dependency-free Bayesian comparisons for observed and alternative actions.

Replay actions are observational: an alternative action was not actually
performed in the same state.  This module therefore compares posterior
success probabilities and reports uncertainty instead of asserting that an
alternative was objectively better.  Independent Beta posteriors are sampled
with a seeded ``random.Random`` instance so reports are reproducible without
NumPy or SciPy.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "bayesian_action_decision_v1"


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("cannot calculate a quantile from no samples")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


@dataclass(frozen=True, slots=True)
class BetaPosterior:
    """Beta posterior for a binary action outcome."""

    successes: float
    failures: float
    prior_alpha: float = 1.0
    prior_beta: float = 1.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.successes) or not math.isfinite(self.failures):
            raise ValueError("successes and failures must be finite")
        if self.successes < 0 or self.failures < 0:
            raise ValueError("successes and failures must be non-negative")
        if self.prior_alpha <= 0 or self.prior_beta <= 0:
            raise ValueError("Beta prior parameters must be positive")

    @property
    def alpha(self) -> float:
        return self.prior_alpha + self.successes

    @property
    def beta(self) -> float:
        return self.prior_beta + self.failures

    @property
    def support(self) -> float:
        return self.successes + self.failures

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        total = self.alpha + self.beta
        return self.alpha * self.beta / (total * total * (total + 1.0))

    def sample(self, generator: random.Random) -> float:
        return generator.betavariate(self.alpha, self.beta)

    def as_dict(self) -> dict[str, Any]:
        return {
            "successes": self.successes,
            "failures": self.failures,
            "support": self.support,
            "prior_alpha": self.prior_alpha,
            "prior_beta": self.prior_beta,
            "posterior_alpha": self.alpha,
            "posterior_beta": self.beta,
            "mean": self.mean,
            "variance": self.variance,
        }


def _posterior(
    counts: Mapping[str, Any],
    *,
    prior_alpha: float,
    prior_beta: float,
) -> BetaPosterior:
    try:
        successes = float(counts.get("successes", counts.get("wins", 0)))
        failures = float(counts.get("failures", counts.get("losses", 0)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise TypeError("action counts must contain integer successes/failures") from exc
    return BetaPosterior(successes, failures, prior_alpha, prior_beta)


def posterior_from_probability(
    probability: float,
    support: float,
    *,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> BetaPosterior:
    """Create an effective-count posterior from a model probability.

    This is useful when the harness has a candidate probability and support
    rather than raw success/failure counts.  ``support`` is treated as a
    fractional effective sample size; raw replay counts should use
    :func:`compare_action_counts` instead.
    """

    if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in the range [0, 1]")
    if not math.isfinite(support) or support < 0:
        raise ValueError("support must be finite and non-negative")
    return BetaPosterior(
        probability * support,
        (1.0 - probability) * support,
        prior_alpha,
        prior_beta,
    )


def _compare_posterior_objects(
    observed_posterior: BetaPosterior,
    alternative_posterior: BetaPosterior,
    *,
    epsilon: float,
    credible_level: float,
    samples: int,
    seed: int,
) -> dict[str, Any]:
    """Sample two already-constructed posterior distributions."""

    if not 0 <= epsilon < 1:
        raise ValueError("epsilon must be in the range [0, 1)")
    if not 0 < credible_level < 1:
        raise ValueError("credible_level must be between zero and one")
    if samples <= 0:
        raise ValueError("samples must be positive")
    if not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    generator = random.Random(seed)
    observed_draws: list[float] = []
    alternative_draws: list[float] = []
    differences: list[float] = []
    regrets: list[float] = []
    margin_regrets: list[float] = []
    wins = 0
    for _ in range(samples):
        observed_probability = observed_posterior.sample(generator)
        alternative_probability = alternative_posterior.sample(generator)
        difference = alternative_probability - observed_probability
        observed_draws.append(observed_probability)
        alternative_draws.append(alternative_probability)
        differences.append(difference)
        regrets.append(max(0.0, difference))
        margin_regrets.append(max(0.0, difference - epsilon))
        if difference > epsilon:
            wins += 1
    tail = (1.0 - credible_level) / 2.0
    observed_interval = [_quantile(observed_draws, tail), _quantile(observed_draws, 1.0 - tail)]
    alternative_interval = [_quantile(alternative_draws, tail), _quantile(alternative_draws, 1.0 - tail)]
    difference_interval = [_quantile(differences, tail), _quantile(differences, 1.0 - tail)]
    probability = wins / samples
    return {
        "schema_version": SCHEMA_VERSION,
        "epsilon": epsilon,
        "credible_level": credible_level,
        "monte_carlo_samples": samples,
        "seed": seed,
        "observed": observed_posterior.as_dict(),
        "alternative": alternative_posterior.as_dict(),
        "probability_alternative_beats_observed": probability,
        "probability_alternative_beats_by_epsilon": probability,
        "probability_alternative_beats": probability,
        "probability_alternative_better": probability,
        "expected_regret": sum(regrets) / samples,
        "expected_regret_after_epsilon": sum(margin_regrets) / samples,
        "expected_difference": sum(differences) / samples,
        "posterior_mean_difference": sum(differences) / samples,
        "observed_credible_interval": observed_interval,
        "alternative_credible_interval": alternative_interval,
        "difference_credible_interval": difference_interval,
        "credible_interval": difference_interval,
        "estimate_type": "posterior_success_probability_comparison",
        "interpretation": (
            "The alternative is probabilistically better under the supplied "
            "Beta priors and observational counts; this is not causal proof."
        ),
    }


def compare_posteriors(
    observed: BetaPosterior,
    alternative: BetaPosterior,
    *,
    epsilon: float = 0.0,
    credible_level: float = 0.95,
    samples: int = 20_000,
    seed: int = 7,
) -> dict[str, Any]:
    """Compare two posteriors directly, preserving their individual priors."""

    if not isinstance(observed, BetaPosterior) or not isinstance(alternative, BetaPosterior):
        raise TypeError("observed and alternative must be BetaPosterior instances")
    return _compare_posterior_objects(
        observed,
        alternative,
        epsilon=epsilon,
        credible_level=credible_level,
        samples=samples,
        seed=seed,
    )


def compare_beta_actions(
    observed: Mapping[str, Any],
    alternative: Mapping[str, Any],
    *,
    epsilon: float = 0.0,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
    credible_level: float = 0.95,
    samples: int = 20_000,
    seed: int = 7,
) -> dict[str, Any]:
    """Compare an alternative action to an observed action.

    ``observed`` and ``alternative`` are mappings containing ``successes`` and
    ``failures`` (``wins``/``losses`` are accepted as aliases).  The primary
    probability is ``P(p_alternative > p_observed + epsilon)``.  ``expected_regret``
    is the posterior expectation of ``max(0, p_alternative - p_observed)``;
    ``expected_regret_after_epsilon`` applies the same practical margin to the
    reported utility gap.  These are success-probability gaps, not proven CS2
    round-value changes.
    """

    observed_posterior = _posterior(
        observed,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
    )
    alternative_posterior = _posterior(
        alternative,
        prior_alpha=prior_alpha,
        prior_beta=prior_beta,
    )
    return _compare_posterior_objects(
        observed_posterior,
        alternative_posterior,
        epsilon=epsilon,
        credible_level=credible_level,
        samples=samples,
        seed=seed,
    )


def compare_action_counts(
    observed_successes: int,
    observed_failures: int,
    alternative_successes: int,
    alternative_failures: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """Convenience wrapper for callers that already have four integer counts."""

    return compare_beta_actions(
        {"successes": observed_successes, "failures": observed_failures},
        {"successes": alternative_successes, "failures": alternative_failures},
        **kwargs,
    )


__all__ = [
    "SCHEMA_VERSION",
    "BetaPosterior",
    "compare_action_counts",
    "compare_beta_actions",
    "compare_posteriors",
    "posterior_from_probability",
]
