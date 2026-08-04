import json
import unittest
from typing import Any

from backend.app.replay.pipeline import (
    extract_players_for_selector,
    stream_replay_pipeline,
)


class ReplayPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw: dict[str, Any] = {
            "schema_version": 1,
            "replay_id": "replay-1",
            "demo_file": "match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 64},
            "rounds": [{"round_num": 1, "start": 100, "end": 300, "winner": "CT"}],
            "damages": [
                {
                    "round_num": 1,
                    "tick": 164,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "T",
                    "victim_side": "CT",
                    "weapon": "ak47",
                    "dmg_health": 20,
                }
            ],
            "kills": [
                {
                    "round_num": 1,
                    "tick": 240,
                    "attacker_steamid": "t1",
                    "victim_steamid": "ct1",
                    "attacker_side": "T",
                    "victim_side": "CT",
                    "weapon": "ak47",
                }
            ],
            "ticks": [
                {"round_num": 1, "tick": 100, "steamid": "t1", "player_name": "T One", "team_name": "T", "health": 100, "alive": True, "X": 1, "Y": 1},
                {"round_num": 1, "tick": 100, "steamid": "ct1", "player_name": "CT One", "team_name": "CT", "health": 100, "alive": True, "X": 2, "Y": 2},
                {"round_num": 1, "tick": 164, "steamid": "t1", "player_name": "T One", "team_name": "T", "health": 100, "alive": True, "X": 1, "Y": 1},
                {"round_num": 1, "tick": 164, "steamid": "ct1", "player_name": "CT One", "team_name": "CT", "health": 80, "alive": True, "X": 2, "Y": 2},
            ],
        }

    def test_selector_contains_player_scoped_references_and_explicit_key_events(self) -> None:
        selector = extract_players_for_selector(self.raw)

        self.assertEqual(selector["schema_version"], "player_selector_v1")
        self.assertEqual({player["player_id"] for player in selector["players"]}, {"t1", "ct1"})
        self.assertEqual(
            {event["key_event_type"] for event in selector["key_events"]},
            {"first_damage_contact", "kill_marker"},
        )
        self.assertTrue(all(event["is_key_event"] for event in selector["key_events"]))
        for player in selector["players"]:
            relevant = {
                event["event_id"]
                for event in selector["events"]
                if player["player_id"] in event["participant_ids"]
            }
            self.assertEqual(set(player["event_ids"]), relevant)
        self.assertEqual(selector["filter_contract"]["global_unfiltered_fields"], ["win_estimator"])

    def test_one_input_pipeline_yields_monotonic_progress_and_global_win_rate(self) -> None:
        updates = list(stream_replay_pipeline(self.raw))

        self.assertEqual(updates[0]["stage"], "received")
        self.assertEqual(updates[-1]["stage"], "complete")
        self.assertTrue(updates[-1]["done"])
        self.assertEqual([item["progress"] for item in updates], sorted(item["progress"] for item in updates))
        result = updates[-1]["result"]
        self.assertEqual(result["win_estimator"]["scope"], "global_team_probability")
        self.assertFalse(result["win_estimator"]["filtered_by_player"])
        self.assertEqual(result["summary"]["anchor"], "first_damage_contact")
        serialized = json.dumps(result)
        for forbidden in ("round_won", "round_winner", '"winner"', '"outcome"'):
            self.assertNotIn(forbidden, serialized)

    def test_missing_damage_stream_keeps_kill_markers_but_abstains_from_coaching(self) -> None:
        replay = {**self.raw, "damages": []}

        result = list(stream_replay_pipeline(replay))[-1]["result"]

        self.assertEqual(result["decision_candidates"], [])
        self.assertFalse(result["summary"]["analysis_available"])
        self.assertEqual(result["summary"]["anchor"], "no_damage_stream")
        self.assertEqual(
            {event["key_event_type"] for event in result["key_events"]},
            {"kill_marker"},
        )


if __name__ == "__main__":
    unittest.main()
