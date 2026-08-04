import json
import tempfile
import unittest
from pathlib import Path

from Noah.training.candidate_labels import extract_candidate_labels
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

    def test_small_model_trains_from_rubric_labels(self) -> None:
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
        second = dict(row)
        second["record_index"] = 1
        second["event"] = {"event_id": "event-2"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "states.json"
            label_path = root / "labels.json"
            state_path.write_text(json.dumps({"rows": [row, second]}), encoding="utf-8")
            label_path.write_text(
                json.dumps(extract_candidate_labels([row, second])),
                encoding="utf-8",
            )

            metrics = train_candidate_models(
                state_path,
                None,
                root / "model",
                labels_path=label_path,
                train_full=False,
            )

            self.assertEqual(metrics["training_target"], "pre_event_suitability")
            self.assertEqual(metrics["candidate_label_schema"], "candidate_label_v1")
            self.assertEqual(metrics["groups_with_label_variance"], 2)
            self.assertTrue(metrics["promotable"])
            self.assertTrue((root / "model" / "small_statistical.json").is_file())


if __name__ == "__main__":
    unittest.main()
