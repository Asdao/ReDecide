"""Fast dependency-free statistical baselines for replay-value rows."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 60.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -60.0))
    return z / (1.0 + z)


class GaussianNaiveBayes:
    """Diagonal Gaussian class model with variance and prior smoothing."""

    def __init__(self, *, variance_floor: float = 1e-6) -> None:
        if variance_floor <= 0:
            raise ValueError("variance_floor must be positive")
        self.variance_floor = variance_floor
        self.classes: tuple[int, ...] = ()
        self.priors: dict[int, float] = {}
        self.means: dict[int, list[float]] = {}
        self.variances: dict[int, list[float]] = {}

    def fit(self, features: Sequence[Sequence[float]], labels: Sequence[int | float]) -> "GaussianNaiveBayes":
        if len(features) != len(labels) or not features:
            raise ValueError("features and labels must have the same non-zero length")
        width = len(features[0])
        if width == 0 or any(len(row) != width for row in features):
            raise ValueError("features must have a consistent non-zero width")
        groups: dict[int, list[Sequence[float]]] = {}
        for row, label in zip(features, labels, strict=True):
            groups.setdefault(int(bool(label)), []).append(row)
        if len(groups) < 2:
            raise ValueError("GaussianNaiveBayes requires both outcome classes")
        self.classes = tuple(sorted(groups))
        total = len(features)
        for label, rows in groups.items():
            self.priors[label] = len(rows) / total
            means = [sum(row[index] for row in rows) / len(rows) for index in range(width)]
            variances = [
                max(
                    self.variance_floor,
                    sum((row[index] - means[index]) ** 2 for row in rows) / len(rows),
                )
                for index in range(width)
            ]
            self.means[label] = means
            self.variances[label] = variances
        return self

    def predict_probability(self, row: Sequence[float]) -> float:
        if not self.classes:
            raise RuntimeError("model has not been fitted")
        log_scores: dict[int, float] = {}
        for label in self.classes:
            score = math.log(max(self.priors[label], 1e-12))
            for value, mean, variance in zip(row, self.means[label], self.variances[label], strict=True):
                score -= 0.5 * (math.log(2.0 * math.pi * variance) + (value - mean) ** 2 / variance)
            log_scores[label] = score
        maximum = max(log_scores.values())
        weights = {label: math.exp(score - maximum) for label, score in log_scores.items()}
        total = sum(weights.values())
        return weights.get(1, 0.0) / total if total else 0.5

    def predict(self, features: Sequence[Sequence[float]]) -> list[float]:
        return [self.predict_probability(row) for row in features]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "gaussian_naive_bayes",
            "variance_floor": self.variance_floor,
            "classes": list(self.classes),
            "priors": {str(label): value for label, value in self.priors.items()},
            "means": {str(label): values for label, values in self.means.items()},
            "variances": {str(label): values for label, values in self.variances.items()},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GaussianNaiveBayes":
        model = cls(variance_floor=float(payload.get("variance_floor", 1e-6)))
        model.classes = tuple(int(value) for value in payload.get("classes", []))
        model.priors = {int(label): float(value) for label, value in payload.get("priors", {}).items()}
        model.means = {int(label): [float(value) for value in values] for label, values in payload.get("means", {}).items()}
        model.variances = {
            int(label): [float(value) for value in values]
            for label, values in payload.get("variances", {}).items()
        }
        return model


class LogisticBaseline:
    """Small batch logistic regression trained with deterministic GD."""

    def __init__(self, *, learning_rate: float = 0.05, iterations: int = 80, l2: float = 1e-3) -> None:
        if learning_rate <= 0 or iterations <= 0 or l2 < 0:
            raise ValueError("learning_rate and iterations must be positive; l2 cannot be negative")
        self.learning_rate = learning_rate
        self.iterations = iterations
        self.l2 = l2
        self.means: list[float] = []
        self.scales: list[float] = []
        self.weights: list[float] = []
        self.bias = 0.0

    def _transform(self, row: Sequence[float]) -> list[float]:
        return [(float(value) - mean) / scale for value, mean, scale in zip(row, self.means, self.scales, strict=True)]

    def fit(self, features: Sequence[Sequence[float]], labels: Sequence[int | float]) -> "LogisticBaseline":
        if len(features) != len(labels) or not features:
            raise ValueError("features and labels must have the same non-zero length")
        width = len(features[0])
        if width == 0 or any(len(row) != width for row in features):
            raise ValueError("features must have a consistent non-zero width")
        if len({int(bool(label)) for label in labels}) < 2:
            raise ValueError("LogisticBaseline requires both outcome classes")
        self.means = [sum(float(row[index]) for row in features) / len(features) for index in range(width)]
        self.scales = [
            max(
                1e-9,
                math.sqrt(sum((float(row[index]) - self.means[index]) ** 2 for row in features) / len(features)),
            )
            for index in range(width)
        ]
        transformed = [self._transform(row) for row in features]
        self.weights = [0.0] * width
        self.bias = 0.0
        count = float(len(features))
        binary_labels = [int(bool(label)) for label in labels]
        for _ in range(self.iterations):
            gradient = [0.0] * width
            bias_gradient = 0.0
            for row, label in zip(transformed, binary_labels, strict=True):
                error = _sigmoid(self.bias + sum(weight * value for weight, value in zip(self.weights, row, strict=True))) - label
                bias_gradient += error
                for index, value in enumerate(row):
                    gradient[index] += error * value
            self.bias -= self.learning_rate * bias_gradient / count
            for index in range(width):
                self.weights[index] -= self.learning_rate * (gradient[index] / count + self.l2 * self.weights[index])
        return self

    def predict_probability(self, row: Sequence[float]) -> float:
        if not self.weights:
            raise RuntimeError("model has not been fitted")
        transformed = self._transform(row)
        return _sigmoid(self.bias + sum(weight * value for weight, value in zip(self.weights, transformed, strict=True)))

    def predict(self, features: Sequence[Sequence[float]]) -> list[float]:
        return [self.predict_probability(row) for row in features]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "logistic_regression",
            "learning_rate": self.learning_rate,
            "iterations": self.iterations,
            "l2": self.l2,
            "means": self.means,
            "scales": self.scales,
            "weights": self.weights,
            "bias": self.bias,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LogisticBaseline":
        model = cls(
            learning_rate=float(payload.get("learning_rate", 0.05)),
            iterations=int(payload.get("iterations", 80)),
            l2=float(payload.get("l2", 1e-3)),
        )
        model.means = [float(value) for value in payload.get("means", [])]
        model.scales = [float(value) for value in payload.get("scales", [])]
        model.weights = [float(value) for value in payload.get("weights", [])]
        model.bias = float(payload.get("bias", 0.0))
        return model
