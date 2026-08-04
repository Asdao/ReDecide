import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Blackbox.training.dataset_split import grouped_split
from Blackbox.training.evaluate_actions import evaluate_actions
from Blackbox.training.evaluate_models import compare_reports
from Blackbox.training.train_action_models import action_state_key


class EvaluationAndActionTests(unittest.TestCase):
    def _rows(self):
        rows = []
        for match in ("m1", "m2", "m3", "m4"):
            for tick, action in enumerate(("hold", "move", "hold")):
                rows.append(
                    {
                        "match_id": match,
                        "map_name": "de_mirage" if match != "m4" else "de_nuke",
                        "side": "ct",
                        "current_zone": "nav_area_1",
                        "action": action,
                        "tick": tick,
                        "legal_actions": ["hold", "move"],
                    }
                )
        return rows

    def test_grouped_split_is_deterministic_and_disjoint(self):
        rows = self._rows()
        train, validation, metadata = grouped_split(rows, seed=11)
        train_again, validation_again, metadata_again = grouped_split(rows, seed=11)
        self.assertEqual([row["match_id"] for row in train], [row["match_id"] for row in train_again])
        self.assertEqual([row["match_id"] for row in validation], [row["match_id"] for row in validation_again])
        self.assertEqual(metadata["split_fingerprint"], metadata_again["split_fingerprint"])
        self.assertTrue(set(metadata["train_groups"]).isdisjoint(metadata["validation_groups"]))

    def test_action_key_contains_map(self):
        row = {"map_name": "de_nuke", "side": "CT", "current_zone": "nav_area_1"}
        self.assertEqual(action_state_key(row), "de_nuke|ct|nav_area_1")

    def test_action_evaluation_is_held_out(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "actions.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in self._rows()) + "\n", encoding="utf-8")
            report = evaluate_actions(input_path=path, seed=3)
        self.assertEqual(report["report_type"], "movement_tendency_held_out")
        self.assertIn("not strategic best move", report["label_semantics"])
        self.assertGreater(report["validation_rows"], 0)
        self.assertIn("training_prior_baseline", report["metrics"])

    def test_model_comparison_rejects_mismatched_metadata(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            common = {
                "feature_schema_version": "v2",
                "dataset_fingerprint": "same",
                "split_fingerprint": "split-a",
                "split_schema_version": "grouped_match_v1",
            }
            first = root / "first.json"
            second = root / "second.json"
            first.write_text(json.dumps({"metadata": common, "models": {"a": {"round": {"log_loss": 0.4}}}}), encoding="utf-8")
            changed = dict(common, split_fingerprint="split-b")
            second.write_text(json.dumps({"metadata": changed, "models": {"b": {"round": {"log_loss": 0.3}}}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                compare_reports([first, second])


if __name__ == "__main__":
    unittest.main()
