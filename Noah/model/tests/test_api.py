import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim import ModelConfig, ReplayModel
from cs2_sim.core.model import (
    ActionFrequencyModel,
    ReplayValueEnsemble,
    SnapshotValueModel,
    ZoneTransitionModel,
)


class ReplayModelApiTests(unittest.TestCase):
    def test_facade_loads_active_release_and_hides_state_keys(self) -> None:
        with TemporaryDirectory() as directory:
            releases = Path(directory) / "releases"
            release = releases / "v1"
            release.mkdir(parents=True)

            bayesian = SnapshotValueModel()
            snapshot = {
                "map_name": "de_mirage",
                "ct_alive": 4,
                "t_alive": 2,
                "label_round_winner": "ct",
            }
            bayesian.observe(snapshot)
            bayesian_path = release / "small_snapshot_value.json"
            bayesian.save(bayesian_path)
            ReplayValueEnsemble(booster_weight=0.0).save_manifest(
                release / "full_replay_value.manifest.json",
                bayesian_path=bayesian_path,
            )

            actions = ActionFrequencyModel()
            actions.observe("de_mirage|ct|A_SITE", "hold")
            actions.save(release / "action_frequency.json")
            transitions = ZoneTransitionModel()
            transitions.observe("A_SITE", "A_MAIN", side="ct", map_name="de_mirage")
            transitions.save(release / "zone_transitions.json")
            (releases / "current.json").write_text(json.dumps({"version": "v1"}), encoding="utf-8")

            model = ReplayModel.load(ModelConfig(releases_dir=releases))
            prediction = model.predict(snapshot)
            self.assertGreater(prediction.probability, 0.5)
            self.assertEqual(
                model.choose_action(
                    map_name="de_mirage",
                    side="ct",
                    zone="A_SITE",
                    legal_actions=["hold", "move"],
                ),
                "hold",
            )
            self.assertEqual(
                model.predict_next_zone("A_SITE", map_name="de_mirage", side="ct"),
                "A_MAIN",
            )
            ranked = model.rank_candidate_actions(
                [
                    {"action": "hold", "death_probability": 0.2, "round_value_delta": 0.1, "sample_count": 10, "entropy": 0.2},
                    {"action": "peek", "death_probability": 0.7, "round_value_delta": -0.1, "sample_count": 10, "entropy": 0.2},
                ]
            )
            self.assertEqual(ranked[0]["action"], "hold")
            self.assertTrue(model.status.has_action_model)
            self.assertTrue(model.status.has_transition_model)
            self.assertFalse(model.status.has_engagement_model)
            self.assertFalse(model.status.has_engagement_booster)

            report = model.analyse_match(
                {
                    "demo_file": "fixture.dem",
                    "header": {"map_name": "de_mirage", "tick_rate": 10},
                    "rounds": [{"round_num": 1, "start": 0, "end": 10, "winner": "ct"}],
                    "ticks": [
                        {"round_num": 1, "tick": 0, "team_name": "CT", "health": 100},
                        {"round_num": 1, "tick": 0, "team_name": "T", "health": 100},
                    ],
                    "kills": [],
                    "damages": [],
                    "bomb": [],
                },
                max_timeline_points=2,
            )
            self.assertEqual(report["report_type"], "full_match_timeline")

            engagement_report = model.analyse_engagement(
                {
                    "demo_file": "fixture.dem",
                    "header": {"map_name": "de_mirage", "tick_rate": 10},
                    "rounds": [{"round_num": 1, "start": 0, "end": 20, "winner": "ct"}],
                    "damages": [
                        {
                            "round_num": 1,
                            "tick": 1,
                            "attacker_steamid": "t1",
                            "victim_steamid": "ct1",
                            "attacker_side": "t",
                            "victim_side": "ct",
                            "weapon": "ak47",
                        }
                    ],
                    "kills": [],
                },
                player_id="t1",
                horizon_seconds=(1.0,),
            )
            self.assertEqual(engagement_report["report_type"], "engagement_analysis")
            self.assertEqual(engagement_report["summary"]["row_count"], 1)
            self.assertFalse(engagement_report["model_available"])


if __name__ == "__main__":
    unittest.main()
