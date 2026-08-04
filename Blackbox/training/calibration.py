"""Probability calibration helpers with no optional dependencies."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any


def _logit(probability: float) -> float:
    clipped = min(1.0 - 1e-7, max(1e-7, float(probability)))
    return math.log(clipped / (1.0 - clipped))


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(value, 60.0))
        return 1.0 / (1.0 + z)
    z = math.exp(max(value, -60.0))
    return z / (1.0 + z)


class PlattCalibrator:
    """Fit ``sigmoid(scale * logit(p) + bias)`` using Newton updates."""

    def __init__(self, *, iterations: int = 50, l2: float = 1e-3) -> None:
        self.iterations = iterations
        self.l2 = l2
        self.scale = 1.0
        self.bias = 0.0

    def fit(self, probabilities: Sequence[float], labels: Sequence[int | float]) -> "PlattCalibrator":
        if len(probabilities) != len(labels) or not probabilities:
            raise ValueError("probabilities and labels must have the same non-zero length")
        if len({int(bool(label)) for label in labels}) < 2:
            raise ValueError("calibration requires both outcome classes")
        logits = [_logit(value) for value in probabilities]
        binary_labels = [int(bool(label)) for label in labels]
        for _ in range(self.iterations):
            gradient_scale = self.l2 * self.scale
            gradient_bias = 0.0
            hessian_scale = self.l2
            hessian_bias = self.l2
            cross = 0.0
            for feature, label in zip(logits, binary_labels, strict=True):
                prediction = _sigmoid(self.scale * feature + self.bias)
                error = prediction - label
                curvature = max(1e-8, prediction * (1.0 - prediction))
                gradient_scale += error * feature
                gradient_bias += error
                hessian_scale += curvature * feature * feature
                hessian_bias += curvature
                cross += curvature * feature
            determinant = hessian_scale * hessian_bias - cross * cross
            if determinant <= 1e-12:
                break
            delta_scale = (gradient_scale * hessian_bias - gradient_bias * cross) / determinant
            delta_bias = (gradient_bias * hessian_scale - gradient_scale * cross) / determinant
            self.scale -= delta_scale
            self.bias -= delta_bias
            if abs(delta_scale) + abs(delta_bias) < 1e-7:
                break
        return self

    def predict(self, probabilities: Sequence[float]) -> list[float]:
        return [_sigmoid(self.scale * _logit(value) + self.bias) for value in probabilities]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "platt",
            "version": 1,
            "iterations": self.iterations,
            "l2": self.l2,
            "scale": self.scale,
            "bias": self.bias,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlattCalibrator":
        model = cls(iterations=int(payload.get("iterations", 50)), l2=float(payload.get("l2", 1e-3)))
        model.scale = float(payload.get("scale", 1.0))
        model.bias = float(payload.get("bias", 0.0))
        return model
