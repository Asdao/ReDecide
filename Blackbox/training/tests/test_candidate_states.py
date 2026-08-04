import json
import tempfile
import unittest
from pathlib import Path

from Blackbox.training.candidate_states import (
    CANDIDATE_STATE_SCHEMA_VERSION,
    extract_candidate_state_report,
    load_replay_records,
    write_candidate_states,
)


class CandidateStateExtractionTests(unittest.TestCase):
    @staticmethod
    def _fixture() -> dict:
        path = Path(__file__).resolve().parents[3] / "backend" / "tests" / "fixtures" / "coach_full_replay.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_emits_one_leakage_safe_row_per_fixture_kill(self) -> None:
        report = extract_candidate_state_report([self._fixture()])
        self.assertEqual(report.summary()["schema_version"], CANDIDATE_STATE_SCHEMA_VERSION)
        self.assertEqual(report.kills_seen, 4)
        self.assertEqual(len(report.rows), 4)
        first = report.rows[0]
        self.assertEqual(first["decision_tick"], 64)
        self.assertEqual(first["event"]["victim_id"], "t1")
        self.assertIn("hold", first["legal_actions"])
        self.assertEqual(set(first["legal_actions"]), set(first["action_features"]))
        # The same-tick victim death exists in the fixture, but cannot enter
        # the decision state because only strictly earlier snapshots qualify.
        victim = next(player for player in first["state"]["players"] if player["player_id"] == "t1")
        self.assertTrue(victim["alive"])
        self.assertEqual(victim["health"], 100)
        self.assertNotIn("winner", json.dumps(first["state"], sort_keys=True))
        json.dumps(first)  # all enums/features must be JSON serializable

    def test_no_prior_snapshot_abstains_instead_of_using_same_tick_state(self) -> None:
        record = self._fixture()
        record["kills"] = record["kills"][:1]
        record["events"] = {}
        record["ticks"] = [row for row in record["ticks"] if row["tick"] == 64]
        report = extract_candidate_state_report([record])
        self.assertEqual(report.kills_seen, 1)
        self.assertEqual(report.rows, ())
        self.assertEqual(
            report.summary()["skip_reasons"],
            {"missing_strict_pre_event_snapshot": 1},
        )

    def test_kill_and_player_death_streams_are_deduplicated(self) -> None:
        record = self._fixture()
        record["events"] = {
            "player_death": [dict(kill) for kill in record["kills"]],
        }
        report = extract_candidate_state_report([record])
        self.assertEqual(report.kills_seen, 4)
        self.assertEqual(len(report.rows), 4)

    def test_raw_player_death_user_alias_is_normalized(self) -> None:
        record = self._fixture()
        record["kills"] = []
        record["events"] = {
            "player_death": [
                {
                    "round_num": 1,
                    "tick": 64,
                    "attacker_steamid": "ct1",
                    "user_steamid": "t1",
                    "weapon": "m4a1",
                }
            ]
        }
        report = extract_candidate_state_report([record])
        self.assertEqual(report.rows[0]["event"]["victim_id"], "t1")

    def test_json_and_jsonl_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            source.write_text(json.dumps(self._fixture()), encoding="utf-8")
            json_output = root / "candidate.json"
            jsonl_output = root / "candidate.jsonl"
            json_report = write_candidate_states(source, json_output)
            write_candidate_states(source, jsonl_output)
            payload = json.loads(json_output.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"], json_report.summary())
            self.assertEqual(len(jsonl_output.read_text(encoding="utf-8").splitlines()), 4)
            self.assertEqual(len(load_replay_records(jsonl_output)), 4)


if __name__ == "__main__":
    unittest.main()
