import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Noah.training.train_engagement_model import train_engagement_model


class EngagementTrainerTests(unittest.TestCase):
    def test_grouped_training_writes_artifact_and_metrics(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "engagement.jsonl"
            rows = []
            for match_id, death in (("m1", False), ("m2", True), ("m3", False)):
                rows.append(
                    {
                        "match_id": match_id,
                        "source": f"{match_id}.dem",
                        "round_num": 1,
                        "anchor_tick": 10,
                        "player_id": "p",
                        "map_name": "de_mirage",
                        "side": "ct",
                        "role": "attacker",
                        "horizon_seconds": 2.0,
                        "features": {"anchor_kind": "damage", "weapon": "ak47"},
                        "label_kill": not death,
                        "label_death": death,
                        "label_trade": False,
                    }
                )
            source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            output = root / "engagement_model.json"
            metrics_path = root / "metrics.json"
            metrics = train_engagement_model(source, output, metrics_path=metrics_path, validation_fraction=0.34)
            self.assertTrue(output.is_file())
            self.assertTrue(metrics_path.is_file())
            self.assertEqual(metrics["rows"]["total"], 3)
            self.assertEqual(len(metrics["groups"]["validation_ids"]), 1)
            self.assertEqual(metrics["groups"]["training"] + metrics["groups"]["validation"], 3)
            self.assertIn("kill", metrics["targets"])


if __name__ == "__main__":
    unittest.main()
