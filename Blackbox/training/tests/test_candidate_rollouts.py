import json
import unittest
from pathlib import Path

from Blackbox.training.candidate_rollouts import (
    ROLLOUT_SCHEMA_VERSION,
    generate_rollouts,
)
from Blackbox.training.candidate_states import extract_candidate_state_report


class CandidateRolloutTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> dict:
        path = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "coach_full_replay.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_aggregates_legal_action_outcomes(self) -> None:
        rows = extract_candidate_state_report([self._fixture()]).rows
        outcomes = generate_rollouts(rows[:1], rollouts=2, seed=7)

        self.assertEqual(len(outcomes), len(rows[0]["legal_actions"]))
        self.assertTrue(all(row["schema_version"] == ROLLOUT_SCHEMA_VERSION for row in outcomes))
        self.assertTrue(all(row["wins"] + row["losses"] == 2 for row in outcomes))
        self.assertTrue(all(0.0 <= row["round_win_probability"] <= 1.0 for row in outcomes))


if __name__ == "__main__":
    unittest.main()
