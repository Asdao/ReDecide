"""Focused regression tests for extractor-to-model input compatibility."""

from __future__ import annotations

import unittest

from training.full_features import record_to_rows
from training.infer_actions import infer_actions
from training.replay_extractor_adapter import normalize_extractor_record
from cs2_sim.core.model.replay_value import ReplayValueEnsemble, snapshot_features


class _FixedBooster:
    def predict(self, rows: list[list[float]]) -> list[float]:
        return [0.61 for _ in rows]


class ModelInputContractTests(unittest.TestCase):
    def _record(self) -> dict:
        return {
            "schema_version": 2,
            "parser": "replacement",
            "demo_file": "sample.dem",
            "header": {"map_name": "de_mirage"},
            "rounds": [{"round_num": 1, "start": 0, "end": 128, "winner": "CT"}],
            "kills": [],
            "damages": [],
            "bomb": [{"round_num": 1, "tick": 64, "event": "bomb_planted", "bombsite": "BombsiteA"}],
            "events": {
                "weapon_fire": [
                    {"round_num": 1, "tick": 64, "weapon": "ak47"},
                    # This event must not leak into round 1's feature count.
                    {"round_num": 2, "tick": 64, "weapon": "ak47"},
                ]
            },
            "ticks": [
                {"round_num": 1, "tick": 64, "steamid": "ct1", "team_name": "CT", "alive": True, "armor": 50},
                {"round_num": 1, "tick": 64, "steamid": "ct2", "team_name": "CT", "alive": False, "armor": 100},
                {"round_num": 1, "tick": 64, "steamid": "t1", "team_name": "T", "health": 100, "armor_value": 25},
            ],
        }

    def test_v2_defaults_tick_rate_and_normalises_features(self) -> None:
        rows = record_to_rows(self._record())
        self.assertEqual(len(rows), 1)
        features = rows[0]["features"]
        # The explicit alive flag is authoritative when health is absent.
        self.assertEqual(features["ct_alive"], 1.0)
        self.assertEqual(features["ct_avg_health"], 100.0)
        self.assertEqual(features["ct_avg_armor"], 50.0)
        self.assertEqual(features["bomb_site_is_a"], 1.0)
        self.assertEqual(features["shots_seen"], 1.0)
        # 64 ticks at the 64 Hz default is one second.
        self.assertEqual(rows[0]["snapshot"]["elapsed_seconds"], 1.0)

    def test_schema_validation_rejects_unknown_and_incomplete_v2(self) -> None:
        with self.assertRaises(ValueError):
            normalize_extractor_record({"schema_version": 99})
        broken = self._record()
        del broken["ticks"]
        with self.assertRaises(ValueError):
            normalize_extractor_record(broken)

    def test_canonical_adapter_keeps_feature_values(self) -> None:
        adapted = normalize_extractor_record(self._record())
        rows = record_to_rows(adapted)
        self.assertEqual(rows[0]["features"]["ct_avg_armor"], 50.0)
        self.assertEqual(rows[0]["features"]["bomb_site_is_a"], 1.0)
        self.assertEqual(adapted["header"]["tick_rate"], 64.0)

    def test_actions_honor_alive_without_health_and_use_64hz_default(self) -> None:
        record = {
            "header": {},
            "rounds": [{"round_num": 1, "start": 0, "end": 128, "winner": "ct"}],
            "ticks": [
                {"round_num": 1, "tick": 0, "steamid": "p", "team_name": "CT", "alive": True, "X": 0, "Y": 0},
                {"round_num": 1, "tick": 64, "steamid": "p", "team_name": "CT", "alive": True, "X": 30, "Y": 0},
            ],
        }
        rows = infer_actions(record, movement_threshold=20.0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["horizon_ticks"], 64)
        self.assertEqual(rows[0]["action"], "move")

    def test_runtime_prediction_uses_the_same_vector_as_training(self) -> None:
        row = record_to_rows(self._record())[0]
        vector = [row["features"][name] for name in ReplayValueEnsemble().feature_names]
        self.assertEqual(vector, snapshot_features(row["snapshot"]))
        model = ReplayValueEnsemble(booster=_FixedBooster(), booster_weight=1.0)
        direct = model.predict_features(vector, snapshot=row["snapshot"])
        snapshot_prediction = model.predict(row["snapshot"])
        self.assertEqual(direct.probability, snapshot_prediction.probability)


if __name__ == "__main__":
    unittest.main()
