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
            self.assertTrue(model.status.has_action_model)
            self.assertTrue(model.status.has_transition_model)


if __name__ == "__main__":
    unittest.main()
