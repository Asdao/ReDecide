import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from cs2_sim.core.model import EngagementModel


class EngagementModelTests(unittest.TestCase):
    def _row(self, **overrides):
        row = {
            "map_name": "de_mirage",
            "side": "ct",
            "role": "victim",
            "horizon_seconds": 2.0,
            "features": {"anchor_kind": "damage", "weapon": "ak47"},
            "label_kill": False,
            "label_death": True,
            "label_trade": True,
            "survived_after_kill": None,
            "round_value_delta": -0.1,
        }
        row.update(overrides)
        return row

    def test_beta_smoothing_support_and_round_trip(self):
        model = EngagementModel(alpha=1.0, min_support=2)
        prior = model.predict(self._row())
        self.assertAlmostEqual(prior.kill_probability, 0.5)
        self.assertFalse(prior.supported)
        model.observe(self._row())
        model.observe(self._row())
        prediction = model.predict(self._row())
        self.assertGreater(prediction.death_probability, prediction.kill_probability)
        self.assertTrue(prediction.supported)
        self.assertAlmostEqual(prediction.round_value_delta, -0.1)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "engagement.json"
            model.save(path)
            restored = EngagementModel.load(path)
            self.assertEqual(restored.predict_dict(self._row()), model.predict_dict(self._row()))


if __name__ == "__main__":
    unittest.main()
