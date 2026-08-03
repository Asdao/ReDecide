import json
import tempfile
import unittest
from pathlib import Path

from Noah.training.candidate_rollouts import generate_rollouts
from Noah.training.candidate_states import extract_candidate_state_report
from Noah.training.train_candidate_value import train_candidate_models


class CandidateTrainingTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> dict:
        path = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "coach_full_replay.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_small_model_trains_from_aggregated_rollouts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "states.json"
            rollout_path = root / "rollouts.jsonl"
            state_report = extract_candidate_state_report([self._fixture()])
            state_path.write_text(json.dumps(state_report.to_dict()), encoding="utf-8")
            rollout_path.write_text(
                "".join(json.dumps(row) + "\n" for row in generate_rollouts(state_report.rows, rollouts=2)),
                encoding="utf-8",
            )

            metrics = train_candidate_models(state_path, rollout_path, root / "model", train_full=False)

            self.assertFalse(metrics["full_trained"])
            self.assertTrue((root / "model" / "small_statistical.json").is_file())
            self.assertEqual(metrics["rollout_rows"], 24)
            self.assertEqual(metrics["groups_with_action_outcome_variance"], 0)
            self.assertTrue(metrics["rollout_quality_warnings"])
            self.assertFalse(metrics["promotable"])
            self.assertFalse(metrics["heldout_split_valid"])
            self.assertEqual(
                metrics["candidate_model_status"],
                "statistical_prior_only_no_counterfactual_signal",
            )


if __name__ == "__main__":
    unittest.main()
