"""First-order Markov transition model for replay movement zones."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class ZoneTransitionModel:
    """Estimate the next zone from a previous zone and optional side."""

    def __init__(self, *, alpha: float = 1.0) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        self.alpha = alpha
        self._counts: dict[str, dict[str, int]] = {}
        self._zones: set[str] = set()

    @staticmethod
    def state_key(zone: str | None, side: str | None = None) -> str:
        return f"{str(side or 'unknown').lower()}|{str(zone or 'unknown')}"

    def observe(self, previous_zone: str | None, next_zone: str | None, *, side: str | None = None) -> None:
        source = str(previous_zone or "unknown")
        destination = str(next_zone or "unknown")
        key = self.state_key(source, side)
        self._counts.setdefault(key, {})[destination] = self._counts.setdefault(key, {}).get(destination, 0) + 1
        self._zones.update((source, destination))

    @property
    def state_count(self) -> int:
        return len(self._counts)

    @property
    def zones(self) -> tuple[str, ...]:
        return tuple(sorted(self._zones))

    def probabilities(self, previous_zone: str | None, *, side: str | None = None) -> dict[str, float]:
        if not self._zones:
            return {}
        key = self.state_key(previous_zone, side)
        counts = self._counts.get(key, {})
        denominator = sum(counts.values()) + self.alpha * len(self._zones)
        return {
            zone: (counts.get(zone, 0) + self.alpha) / denominator
            for zone in sorted(self._zones)
        }

    def predict_next(self, previous_zone: str | None, *, side: str | None = None) -> str:
        probabilities = self.probabilities(previous_zone, side=side)
        if not probabilities:
            return str(previous_zone or "unknown")
        return max(probabilities, key=lambda zone: (probabilities[zone], zone))

    def fit_sequences(self, sequences: Iterable[Iterable[tuple[str | None, str | None, str | None]]]) -> "ZoneTransitionModel":
        for sequence in sequences:
            for previous_zone, next_zone, side in sequence:
                self.observe(previous_zone, next_zone, side=side)
        return self

    def to_dict(self) -> dict[str, object]:
        return {"version": 1, "alpha": self.alpha, "counts": self._counts, "zones": sorted(self._zones)}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ZoneTransitionModel":
        model = cls(alpha=float(payload.get("alpha", 1.0)))
        model._counts = {
            str(key): {str(zone): int(count) for zone, count in values.items()}
            for key, values in (payload.get("counts") or {}).items()
        }
        model._zones = {str(zone) for zone in (payload.get("zones") or [])}
        return model

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ZoneTransitionModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
