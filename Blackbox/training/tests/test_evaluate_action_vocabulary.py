import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from Blackbox.training.evaluate_action_vocabulary import evaluate_action_vocabulary


class ActionVocabularyEvaluationTests(unittest.TestCase):
    def test_report_counts_canonical_actions_and_marks_rare_actions(self):
        rows = []
        for index, action in enumerate(("hold", "move", "peek", "plant")):
            rows.append(
                {
                    "source": f"match-{index}",
                    "observed_action": action,
                    "label_kill": index % 2 == 0,
                    "label_death": index % 2 == 1,
                }
            )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "windows.jsonl"
            source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            report = evaluate_action_vocabulary(source, root / "coverage.json", min_samples=1)
        self.assertEqual(report["observed_action_counts"]["move_to_adjacent_zone"], 1)
        self.assertTrue(report["actions"]["hold"]["supported_for_training"])
        self.assertIn("plant", report["actions"])


if __name__ == "__main__":
    unittest.main()
