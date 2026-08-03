import json
import tempfile
import unittest
from pathlib import Path

from Noah.training.candidate_rollouts import generate_rollouts
from Noah.training.candidate_states import extract_candidate_state_report
from Noah.training.evaluate_candidate_value import evaluate_candidate_value
from Noah.training.train_candidate_value import train_candidate_models


class CandidateEvaluationTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> dict:
        path = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "coach_full_replay.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_reports_probability_and_support_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            states = extract_candidate_state_report([self._fixture()])
            state_path = root / "states.json"
            rollout_path = root / "rollouts.jsonl"
            state_path.write_text(json.dumps(states.to_dict()), encoding="utf-8")
            rollout_path.write_text(
                "".join(json.dumps(row) + "\n" for row in generate_rollouts(states.rows, rollouts=2)),
                encoding="utf-8",
            )
            model_dir = root / "model"
            train_candidate_models(state_path, rollout_path, model_dir, train_full=False)

            result = evaluate_candidate_value(state_path, rollout_path, model_dir)

            self.assertEqual(result["candidate_states"], 4)
            self.assertGreater(result["observations"], 0)
            self.assertIsNotNone(result["brier"])
            self.assertIsNotNone(result["log_loss"])
            self.assertEqual(result["groups_with_empirical_action_variance"], 0)
            self.assertTrue(result["quality_warnings"])
            self.assertIsNone(result["top1_empirical_match_rate"])
            self.assertEqual(result["quality_status"], "not_comparable_no_heldout_split")
            self.assertFalse(result["heldout_split_valid"])


if __name__ == "__main__":
    unittest.main()
