import json
import tempfile
import unittest
from pathlib import Path

from Noah.training.candidate_labels import extract_candidate_labels
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

    def test_reports_rubric_label_metrics(self) -> None:
        row = {
            "schema_version": "candidate_state_v1",
            "source": "rubric-match.dem",
            "record_index": 0,
            "actor_id": "ct1",
            "decision_tick": 100,
            "event": {"event_id": "event-1"},
            "legal_actions": ["hold", "peek", "move_to_adjacent_zone:A_MAIN"],
            "action_features": {
                "hold": {"visible_enemies": 1.0},
                "peek": {"visible_enemies": 1.0},
                "move_to_adjacent_zone:A_MAIN": {"visible_enemies": 1.0},
            },
            "state": {
                "players": [
                    {"player_id": "ct1", "team": "ct", "health": 100, "alive": True},
                    {"player_id": "ct2", "team": "ct", "health": 100, "alive": True},
                    {"player_id": "t1", "team": "t", "health": 100, "alive": True},
                ],
                "bomb_state": "none",
                "bomb_time_remaining": None,
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "states.json"
            labels_path = root / "labels.json"
            state_path.write_text(json.dumps({"rows": [row]}), encoding="utf-8")
            labels_path.write_text(
                json.dumps(extract_candidate_labels([row])),
                encoding="utf-8",
            )
            model_dir = root / "model"
            train_candidate_models(
                state_path,
                None,
                model_dir,
                labels_path=labels_path,
                train_full=False,
            )
            result = evaluate_candidate_value(
                state_path,
                None,
                model_dir,
                labels_path=labels_path,
            )

            self.assertEqual(result["evaluation_target"], "pre_event_suitability")
            self.assertEqual(result["label_schema"], "candidate_label_v1")
            self.assertEqual(result["comparable_state_groups"], 1)
            self.assertIsNotNone(result["top1_label_match_rate"])


if __name__ == "__main__":
    unittest.main()
