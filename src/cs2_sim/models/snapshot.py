"""Small Bayesian value model for extracted replay snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SnapshotValueModel:
    """Hierarchically smoothed estimate of CT round-win probability.

    Exact CS2 states are sparse, even with thousands of rounds.  The model
    therefore backs off from an exact state to progressively broader buckets
    instead of returning an uninformative 50/50 estimate for every unseen
    combination.
    """

    def __init__(
        self,
        *,
        alpha: float = 1.0,
        beta: float = 1.0,
        prior_strength: float = 8.0,
    ) -> None:
        if alpha <= 0 or beta <= 0 or prior_strength <= 0:
            raise ValueError("alpha, beta, and prior_strength must be positive")
        self.alpha = alpha
        self.beta = beta
        self.prior_strength = prior_strength
        self._counts: dict[str, list[int]] = {}

    @staticmethod
    def state_key(snapshot: dict[str, Any]) -> str:
        """Return the most-specific state key for compatibility and inspection."""

        return SnapshotValueModel.state_keys(snapshot)[-1]

    @staticmethod
    def state_keys(snapshot: dict[str, Any]) -> tuple[str, ...]:
        """Return state keys ordered from broadest to most specific."""

        elapsed_bucket = int(float(snapshot.get("elapsed_seconds") or 0.0) // 10)
        kills_bucket = min(5, int(snapshot.get("kills_seen") or 0))
        map_name = str(snapshot.get("map_name") or "unknown")
        event_type = str(snapshot.get("event_type") or "unknown")
        ct_alive = int(snapshot.get("ct_alive") or 0)
        t_alive = int(snapshot.get("t_alive") or 0)
        bomb_planted = bool(snapshot.get("bomb_planted"))
        bomb_site = str(snapshot.get("bomb_site") or "none")
        alive_difference = max(-5, min(5, ct_alive - t_alive))
        phase_bucket = min(3, elapsed_bucket // 3)
        return (
            "global",
            f"map|{map_name}",
            f"coarse|{alive_difference}|{bomb_planted}|{phase_bucket}",
            f"state|{ct_alive}|{t_alive}|{bomb_planted}|{elapsed_bucket}|{kills_bucket}",
            "exact|"
            + "|".join(
                (
                    map_name,
                    event_type,
                    str(ct_alive),
                    str(t_alive),
                    str(bomb_planted),
                    bomb_site,
                    str(elapsed_bucket),
                    str(kills_bucket),
                )
            ),
        )

    def observe(self, snapshot: dict[str, Any]) -> None:
        winner = snapshot.get("label_round_winner")
        if winner not in {"ct", "t"}:
            return
        index = 0 if winner == "ct" else 1
        for key in self.state_keys(snapshot):
            self._counts.setdefault(key, [0, 0])[index] += 1

    def predict_ct_win(self, snapshot: dict[str, Any]) -> float:
        probability = self.alpha / (self.alpha + self.beta)
        for key in self.state_keys(snapshot):
            wins, losses = self._counts.get(key, [0, 0])
            samples = wins + losses
            if samples:
                probability = (wins + self.prior_strength * probability) / (
                    samples + self.prior_strength
                )
        return probability

    def sample_count(self, snapshot: dict[str, Any]) -> int:
        return sum(self._counts.get(self.state_keys(snapshot)[-1], [0, 0]))

    def global_sample_count(self) -> int:
        """Return the number of labelled observations seen by the model."""

        return sum(self._counts.get("global", [0, 0]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 2,
            "alpha": self.alpha,
            "beta": self.beta,
            "prior_strength": self.prior_strength,
            "counts": self._counts,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SnapshotValueModel:
        model = cls(
            alpha=float(payload["alpha"]),
            beta=float(payload["beta"]),
            prior_strength=float(payload.get("prior_strength", 8.0)),
        )
        counts = {
            str(key): [int(values[0]), int(values[1])]
            for key, values in payload.get("counts", {}).items()
        }
        if int(payload.get("version", 1)) < 2:
            # Version 1 stored only exact buckets.  Preserve those predictions
            # and construct a useful global fallback until the model is retrained.
            counts = {f"exact|{key}": values for key, values in counts.items()}
            counts["global"] = [
                sum(values[0] for key, values in counts.items() if key != "global"),
                sum(values[1] for key, values in counts.items() if key != "global"),
            ]
        model._counts = counts
        return model

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> SnapshotValueModel:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
