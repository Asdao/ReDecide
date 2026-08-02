"""Dependency-free binary probability metrics used by both trainers."""

from __future__ import annotations

import math
from collections.abc import Sequence


def binary_probability_metrics(
    probabilities: Sequence[float],
    labels: Sequence[int | float],
    *,
    baseline_probability: float | None = None,
    calibration_bins: int = 10,
) -> dict[str, float | None | dict[str, float]]:
    """Measure discrimination, calibration, and improvement over a prior.

    ``baseline_probability`` should be estimated from training data rather
    than the validation labels.  That makes the comparison usable on an
    unseen demo split without leaking its class balance.
    """

    if len(probabilities) != len(labels) or not labels:
        raise ValueError("probabilities and labels must have the same non-zero length")
    if calibration_bins <= 0:
        raise ValueError("calibration_bins must be positive")

    eps = 1e-7
    clipped = [min(1.0 - eps, max(eps, float(value))) for value in probabilities]
    binary_labels = [int(bool(value)) for value in labels]
    count = len(binary_labels)
    log_loss = -sum(
        label * math.log(probability) + (1 - label) * math.log(1 - probability)
        for probability, label in zip(clipped, binary_labels, strict=True)
    ) / count
    brier = sum(
        (probability - label) ** 2
        for probability, label in zip(clipped, binary_labels, strict=True)
    ) / count
    predictions = [int(probability >= 0.5) for probability in clipped]
    accuracy = sum(
        prediction == label
        for prediction, label in zip(predictions, binary_labels, strict=True)
    ) / count

    positives = sum(binary_labels)
    negatives = count - positives
    true_positive_rate = (
        sum(prediction == label == 1 for prediction, label in zip(predictions, binary_labels, strict=True))
        / positives
        if positives
        else None
    )
    true_negative_rate = (
        sum(prediction == label == 0 for prediction, label in zip(predictions, binary_labels, strict=True))
        / negatives
        if negatives
        else None
    )
    balanced_accuracy = (
        (true_positive_rate + true_negative_rate) / 2.0
        if true_positive_rate is not None and true_negative_rate is not None
        else None
    )

    calibration_error = 0.0
    for bin_index in range(calibration_bins):
        lower = bin_index / calibration_bins
        upper = (bin_index + 1) / calibration_bins
        members = [
            index
            for index, probability in enumerate(clipped)
            if lower <= probability < upper or (bin_index == calibration_bins - 1 and probability == 1.0)
        ]
        if members:
            mean_probability = sum(clipped[index] for index in members) / len(members)
            mean_label = sum(binary_labels[index] for index in members) / len(members)
            calibration_error += len(members) / count * abs(mean_probability - mean_label)

    result: dict[str, float | None | dict[str, float]] = {
        "log_loss": log_loss,
        "brier": brier,
        "accuracy": accuracy,
        "balanced_accuracy": balanced_accuracy,
        "expected_calibration_error": calibration_error,
        "ct_win_rate": positives / count,
    }
    if baseline_probability is not None:
        baseline = min(1.0 - eps, max(eps, float(baseline_probability)))
        baseline_metrics = binary_probability_metrics(
            [baseline] * count,
            binary_labels,
            calibration_bins=calibration_bins,
        )
        result["training_prior_baseline"] = {
            "probability": baseline,
            "log_loss": float(baseline_metrics["log_loss"]),
            "brier": float(baseline_metrics["brier"]),
            "accuracy": float(baseline_metrics["accuracy"]),
        }
        result["log_loss_improvement"] = float(baseline_metrics["log_loss"]) - log_loss
        result["brier_improvement"] = float(baseline_metrics["brier"]) - brier
    return result
