import json
import tempfile
import unittest
from pathlib import Path

from Blackbox.training.candidate_labels import (
    CANDIDATE_LABEL_SCHEMA_VERSION,
    extract_candidate_labels,
    label_candidate_action,
    write_candidate_labels,
)


class CandidateLabelTests(unittest.TestCase):
    @staticmethod
    def _row(group: int = 0) -> dict:
        return {
            "schema_version": "candidate_state_v1",
            "source": f"match-{group}.dem",
            "record_index": group,
            "actor_id": "ct1",
            "decision_tick": 100,
            "event": {"event_id": f"event-{group}"},
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

    def test_rubric_produces_action_variance_without_future_outcomes(self) -> None:
        row = self._row()
        self.assertEqual(label_candidate_action(row, "peek")["label"], "preferred")
        self.assertEqual(
            label_candidate_action(row, "move_to_adjacent_zone:A_MAIN")["label"],
            "risky",
        )
        labels = extract_candidate_labels([row])
        self.assertEqual(labels["schema_version"], CANDIDATE_LABEL_SCHEMA_VERSION)
        self.assertEqual(labels["summary"]["label_counts"], {"preferred": 1, "risky": 1, "unknown": 1})
        serialized = json.dumps(labels, sort_keys=True).lower()
        self.assertNotIn("winner", serialized)
        self.assertNotIn("round_winner", serialized)
        self.assertNotIn("death", serialized)

    def test_label_sidecar_writes_jsonl_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            states = root / "states.json"
            states.write_text(json.dumps({"rows": [self._row()]}), encoding="utf-8")
            output = root / "labels.jsonl"
            report = write_candidate_labels(states, output)
            self.assertEqual(report["summary"]["label_row_count"], 3)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 3)


if __name__ == "__main__":
    unittest.main()
