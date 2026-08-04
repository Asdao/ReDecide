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
    def state_key(zone: str | None, side: str | None = None, map_name: str | None = None) -> str:
        """Return a map-aware transition key; nav IDs are map-local."""

        return "|".join(
            (
                str(map_name or "unknown").lower(),
                str(side or "unknown").lower(),
                str(zone or "unknown"),
            )
        )

    def observe(
        self,
        previous_zone: str | None,
        next_zone: str | None,
        *,
        side: str | None = None,
        map_name: str | None = None,
    ) -> None:
        source = str(previous_zone or "unknown")
        destination = str(next_zone or "unknown")
        key = self.state_key(source, side, map_name)
        self._counts.setdefault(key, {})[destination] = self._counts.setdefault(key, {}).get(destination, 0) + 1
        self._zones.update((source, destination))

    @property
    def state_count(self) -> int:
        return len(self._counts)

    @property
    def zones(self) -> tuple[str, ...]:
        return tuple(sorted(self._zones))

    def probabilities(
        self,
        previous_zone: str | None,
        *,
        side: str | None = None,
        map_name: str | None = None,
    ) -> dict[str, float]:
        if not self._zones:
            return {}
        key = self.state_key(previous_zone, side, map_name)
        counts = self._counts.get(key, {})
        denominator = sum(counts.values()) + self.alpha * len(self._zones)
        return {
            zone: (counts.get(zone, 0) + self.alpha) / denominator
            for zone in sorted(self._zones)
        }

    def predict_next(
        self,
        previous_zone: str | None,
        *,
        side: str | None = None,
        map_name: str | None = None,
    ) -> str:
        probabilities = self.probabilities(previous_zone, side=side, map_name=map_name)
        if not probabilities:
            return str(previous_zone or "unknown")
        return max(probabilities, key=lambda zone: (probabilities[zone], zone))

    def fit_sequences(self, sequences: Iterable[Iterable[tuple[str | None, ...]]]) -> "ZoneTransitionModel":
        for sequence in sequences:
            for item in sequence:
                if len(item) == 3:
                    previous_zone, next_zone, side = item
                    map_name = None
                elif len(item) == 4:
                    previous_zone, next_zone, side, map_name = item
                else:
                    raise ValueError("transition sequence items must contain 3 or 4 values")
                self.observe(previous_zone, next_zone, side=side, map_name=map_name)
        return self

    def to_dict(self) -> dict[str, object]:
        return {"version": 2, "alpha": self.alpha, "counts": self._counts, "zones": sorted(self._zones)}

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
