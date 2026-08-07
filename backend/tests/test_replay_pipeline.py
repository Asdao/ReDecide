import json
import unittest
from pathlib import Path
from typing import Any

from backend.app.orchestration import _select_diverse_candidates
from backend.app.replay.pipeline import (
    extract_players_for_selector,
    merge_pi_output,
    stream_replay_pipeline,
)
from backend.replay_engine.harness import load_replay_record

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_REPLAY = (
    PROJECT_ROOT / "data" / "private" / "processed" / "full_replays_native_test.jsonl"
)


def _processed_replay(test_case: unittest.TestCase) -> Path:
    if not PROCESSED_REPLAY.is_file():
        test_case.skipTest(f"processed replay JSONL is unavailable: {PROCESSED_REPLAY}")
    return PROCESSED_REPLAY


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

    def test_processed_json_player_selection_analysis_and_output(self) -> None:
        replay = load_replay_record(_processed_replay(self))

        selector = extract_players_for_selector(replay)
        selected_player = next(
            player for player in selector["players"] if player["decision_ids"]
        )
        selected_player_id = selected_player["player_id"]
        selected_decision_id = selected_player["decision_ids"][0]
        player_events = [
            event
            for event in selector["events"]
            if event["event_id"] in selected_player["event_ids"]
        ]

        updates = list(
            stream_replay_pipeline(
                replay,
                decision_id=selected_decision_id,
                sample_every=64,
                max_timeline_points=12,
            )
        )
        output = updates[-1]["result"]

        self.assertEqual(selector["schema_version"], "player_selector_v1")
        self.assertTrue(player_events)
        self.assertTrue(
            all(selected_player_id in event["participant_ids"] for event in player_events)
        )
        progress = [update["progress"] for update in updates]
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(updates[-1]["stage"], "complete")
        self.assertTrue(updates[-1]["done"])
        self.assertEqual(output["selected_decision"]["decision_id"], selected_decision_id)
        self.assertEqual(output["selected_decision"]["player_id"], selected_player_id)
        self.assertIn(
            selected_decision_id,
            {
                candidate["decision_id"]
                for candidate in output["decision_candidates"]
                if candidate["player_id"] == selected_player_id
            },
        )
        self.assertEqual(output["win_estimator"]["scope"], "global_team_probability")
        self.assertFalse(output["win_estimator"]["filtered_by_player"])
        self.assertEqual(output["summary"]["anchor"], "first_damage_contact")
        serialized_decision = json.dumps(output["selected_decision"])
        for forbidden in ("round_won", "round_winner", '"winner"', '"outcome"'):
            self.assertNotIn(forbidden, serialized_decision)

    def test_pi_output_is_merged_with_authoritative_player_identity(self) -> None:
        replay = load_replay_record(_processed_replay(self))
        result = list(stream_replay_pipeline(replay, max_timeline_points=4))[-1]["result"]
        candidate = result["decision_candidates"][0]
        result["selected_decisions"] = [candidate]

        merged = merge_pi_output(
            result,
            """Pi summary:\n```json\n{
              \"decision_id\": \"decision_001\",
              \"observed_action\": \"peek\",
              \"what_could_be_done_better\": \"Hold the angle until support is available.\"
            }\n```""",
        )

        self.assertEqual(merged["coach_analysis"]["decision_id"], candidate["decision_id"])
        self.assertEqual(merged["coach_analysis"]["player_id"], candidate["player_id"])
        self.assertEqual(merged["coach_analysis"]["player_name"], candidate["display_name"])
        self.assertEqual(merged["coach_analysis"]["source"], "pi")
        self.assertEqual(merged["selected_decision"]["decision_id"], candidate["decision_id"])
        self.assertEqual(merged["selected_decision"]["player_name"], candidate["display_name"])
        self.assertNotIn("selected_decisions", merged)
        self.assertNotIn("coach_analysis", result)

    def test_multi_analysis_selection_spans_the_candidate_range(self) -> None:
        candidates = [
            {"decision_id": f"r{round_number}", "round_number": round_number}
            for round_number in range(1, 25)
        ]

        selected = _select_diverse_candidates(candidates, limit=5)

        self.assertEqual(
            [item["round_number"] for item in selected],
            [1, 6, 12, 18, 24],
        )

    def test_multi_analysis_aliases_follow_selected_candidates(self) -> None:
        candidates = [
            {
                "decision_id": f"r{round_number}",
                "round_number": round_number,
                "player_id": "player-1",
                "display_name": "Player One",
            }
            for round_number in range(1, 5)
        ]
        result = {
            "decision_candidates": candidates,
            "selected_decision": candidates[0],
            "selected_decisions": [candidates[0], candidates[3]],
            "players": [{"player_id": "player-1", "display_name": "Player One"}],
        }

        merged = merge_pi_output(
            result,
            {
                "analyses": [
                    {
                        "decision_id": "decision_001",
                        "what_could_be_done_better": "Hold the opening angle.",
                    },
                    {
                        "decision_id": "decision_002",
                        "what_could_be_done_better": "Wait for the late-round rotation.",
                    },
                ]
            },
        )

        self.assertEqual(
            [entry["selected_decision"]["decision_id"] for entry in merged["analyses"]],
            ["r1", "r4"],
        )


if __name__ == "__main__":
    unittest.main()
