"""Small Bayesian value model for extracted replay snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SnapshotValueModel:
    """Beta-binomial estimate of CT round-win probability by state bucket."""

    def __init__(self, *, alpha: float = 1.0, beta: float = 1.0) -> None:
        if alpha <= 0 or beta <= 0:
            raise ValueError("alpha and beta must be positive")
        self.alpha = alpha
        self.beta = beta
        self._counts: dict[str, list[int]] = {}

    @staticmethod
    def state_key(snapshot: dict[str, Any]) -> str:
        elapsed_bucket = int(float(snapshot.get("elapsed_seconds") or 0.0) // 10)
        kills_bucket = min(5, int(snapshot.get("kills_seen") or 0))
        return "|".join(
            (
                str(snapshot.get("map_name") or "unknown"),
                str(snapshot.get("event_type") or "unknown"),
                str(snapshot.get("ct_alive") or 0),
                str(snapshot.get("t_alive") or 0),
                str(bool(snapshot.get("bomb_planted"))),
                str(snapshot.get("bomb_site") or "none"),
                str(elapsed_bucket),
                str(kills_bucket),
            )
        )

    def observe(self, snapshot: dict[str, Any]) -> None:
        winner = snapshot.get("label_round_winner")
        if winner not in {"ct", "t"}:
            return
        row = self._counts.setdefault(self.state_key(snapshot), [0, 0])
        row[0 if winner == "ct" else 1] += 1

    def predict_ct_win(self, snapshot: dict[str, Any]) -> float:
        wins, losses = self._counts.get(self.state_key(snapshot), [0, 0])
        return (wins + self.alpha) / (wins + losses + self.alpha + self.beta)

    def sample_count(self, snapshot: dict[str, Any]) -> int:
        return sum(self._counts.get(self.state_key(snapshot), [0, 0]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "alpha": self.alpha,
            "beta": self.beta,
            "counts": self._counts,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SnapshotValueModel":
        model = cls(alpha=float(payload["alpha"]), beta=float(payload["beta"]))
        model._counts = {
            str(key): [int(values[0]), int(values[1])]
            for key, values in payload.get("counts", {}).items()
        }
        return model

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SnapshotValueModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

