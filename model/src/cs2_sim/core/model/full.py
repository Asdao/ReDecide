"""Optional LightGBM action-value model for the full replay dataset.

LightGBM is imported lazily.  The small statistical model remains usable when
the optional native dependency is not installed or cannot load on a machine.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from ...actions import Action
from ...policy import ActionPolicy
from ...state import GameState
from .features import FEATURE_NAMES, state_action_features
from .small import SmallStatisticalModel


@dataclass(frozen=True, slots=True)
class TrainingExample:
    state: GameState
    player_id: str
    action: Action
    success: bool


class FullLightGBMModel(ActionPolicy):
    """Action scorer that blends LightGBM with the compact statistical model."""

    def __init__(
        self,
        *,
        small_model: SmallStatisticalModel | None = None,
        lightgbm_weight: float = 0.8,
    ) -> None:
        if not 0.0 <= lightgbm_weight <= 1.0:
            raise ValueError("lightgbm_weight must be between 0 and 1")
        self.small_model = small_model or SmallStatisticalModel()
        self.lightgbm_weight = lightgbm_weight
        self._booster = None

    @property
    def is_fitted(self) -> bool:
        return self._booster is not None

    @staticmethod
    def _load_lightgbm():
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise RuntimeError(
                "FullLightGBMModel requires the optional 'full' dependencies; "
                "install with `pip install .[full]`."
            ) from exc
        return lgb

    def fit(
        self,
        examples: Sequence[TrainingExample],
        *,
        validation_examples: Sequence[TrainingExample] | None = None,
        num_boost_round: int = 250,
        update_small_model: bool = False,
    ) -> "FullLightGBMModel":
        """Train on candidate-action rows with binary success labels."""

        if len(examples) < 2:
            raise ValueError("at least two training examples are required")
        labels = [int(example.success) for example in examples]
        if len(set(labels)) < 2:
            raise ValueError("training examples must contain both success classes")
        if num_boost_round <= 0:
            raise ValueError("num_boost_round must be positive")

        if update_small_model:
            for example in examples:
                self.small_model.observe(
                    example.state,
                    example.player_id,
                    example.action,
                    success=example.success,
                )

        lgb = self._load_lightgbm()
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("FullLightGBMModel requires numpy") from exc
        matrix = [
            state_action_features(example.state, example.player_id, example.action)
            for example in examples
        ]
        train_set = lgb.Dataset(
            np.asarray(matrix, dtype=float),
            label=np.asarray(labels, dtype=int),
            feature_name=list(FEATURE_NAMES),
        )
        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 15,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbosity": -1,
            "seed": 7,
        }
        valid_sets = [train_set]
        valid_names = ["train"]
        callbacks = []
        if validation_examples:
            valid_matrix = [
                state_action_features(example.state, example.player_id, example.action)
                for example in validation_examples
            ]
            valid_labels = [int(example.success) for example in validation_examples]
            valid_sets.append(
                lgb.Dataset(
                    np.asarray(valid_matrix, dtype=float),
                    label=np.asarray(valid_labels, dtype=int),
                    reference=train_set,
                    feature_name=list(FEATURE_NAMES),
                )
            )
            valid_names.append("validation")
            callbacks.append(lgb.early_stopping(30, verbose=False))
        self._booster = lgb.train(
            params,
            train_set,
            num_boost_round=num_boost_round,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=callbacks,
        )
        return self

    def _lightgbm_score(self, state: GameState, player_id: str, action: Action) -> float:
        if self._booster is None:
            raise RuntimeError("model has not been fitted or loaded")
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("FullLightGBMModel requires numpy") from exc
        prediction = self._booster.predict(
            np.asarray([state_action_features(state, player_id, action)], dtype=float)
        )[0]
        return float(prediction)

    def predict_probability(
        self,
        state: GameState,
        player_id: str,
        action: Action,
    ) -> float:
        """Return the fitted action-success probability for one candidate."""

        if not self.is_fitted:
            return self.small_model.score_actions(state, player_id, (action,))[action]
        return self._lightgbm_score(state, player_id, action)

    def score_actions(
        self,
        state: GameState,
        player_id: str,
        legal: Iterable[Action],
    ) -> dict[Action, float]:
        legal_actions = tuple(legal)
        if not legal_actions:
            raise ValueError(f"no legal actions for {player_id}")
        if not self.is_fitted:
            return self.small_model.score_actions(state, player_id, legal_actions)

        small_scores = self.small_model.score_actions(state, player_id, legal_actions)
        return {
            action: (
                self.lightgbm_weight * self._lightgbm_score(state, player_id, action)
                + (1.0 - self.lightgbm_weight) * small_scores[action]
            )
            for action in legal_actions
        }

    def choose_action(self, state: GameState, player_id: str, legal: tuple[Action, ...]) -> Action:
        scores = self.score_actions(state, player_id, legal)
        return max(scores, key=lambda action: (scores[action], action.action_type.value, action.target_zone or ""))

    def normalized_entropy(
        self,
        state: GameState,
        player_id: str,
        legal: Iterable[Action],
    ) -> float:
        """Return uncertainty for the same candidate-action distribution."""

        scores = self.score_actions(state, player_id, legal)
        total = sum(scores.values())
        if len(scores) <= 1 or total <= 0:
            return 0.0
        entropy = -sum(
            (score / total) * math.log2(score / total)
            for score in scores.values()
            if score > 0
        )
        return entropy / math.log2(len(scores))

    def save(self, path: str | Path) -> None:
        if self._booster is None:
            raise RuntimeError("cannot save an unfitted LightGBM model")
        model_path = Path(path)
        self._booster.save_model(str(model_path))
        metadata = {
            "version": 1,
            "feature_names": list(FEATURE_NAMES),
            "lightgbm_weight": self.lightgbm_weight,
            "small_model": self.small_model.to_dict(),
        }
        model_path.with_suffix(model_path.suffix + ".json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "FullLightGBMModel":
        model_path = Path(path)
        metadata_path = model_path.with_suffix(model_path.suffix + ".json")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("feature_names") != list(FEATURE_NAMES):
            raise ValueError("model feature schema does not match this application")
        small_payload = metadata.get("small_model")
        small_model = (
            SmallStatisticalModel.from_dict(small_payload)
            if isinstance(small_payload, dict)
            else SmallStatisticalModel()
        )
        model = cls(
            small_model=small_model,
            lightgbm_weight=float(metadata["lightgbm_weight"]),
        )
        model._booster = model._load_lightgbm().Booster(model_file=str(model_path))
        return model
