import unittest
from types import SimpleNamespace

from backend.replay_engine.training.full_match_report import build_full_match_report


class _DeterministicPredictor:
    """Small predictor double with a stable probability from alive counts."""

    feature_names = ()

    def predict(self, snapshot):
        ct = int(snapshot.get("ct_alive") or 0)
        t = int(snapshot.get("t_alive") or 0)
        # Keep values away from the clipping boundary and make swings obvious.
        probability = 0.2 + 0.2 * max(-2, min(2, ct - t))
        return SimpleNamespace(
            probability=probability,
            uncertainty=0.1,
            sample_count=4,
            calibrated=True,
        )


class FullMatchReportTests(unittest.TestCase):
    def _record(self):
        return {
            "schema_version": 2,
            "demo_file": "match.dem",
            "source_path": "fixtures/match.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 10},
            "rounds": [
                {"round_num": 1, "start": 0, "end": 20, "winner": "ct"},
                {"round_num": 2, "start": 20, "end": 40, "winner": "t"},
            ],
            "kills": [
                {
                    "round_num": 1,
                    "tick": 10,
                    "attacker_steamid": "ct1",
                    "victim_steamid": "t1",
                    "attacker_side": "ct",
                    "weapon": "ak47",
                }
            ],
            "damages": [],
            "bomb": [{"round_num": 1, "tick": 15, "event": "bomb_planted", "bombsite": "BombsiteA"}],
            "events": {
                "player_death": [
                    {"round_num": 1, "tick": 10, "victim_steamid": "t1"},
                ],
                "bomb_planted": [
                    {"round_num": 1, "tick": 15, "which_bomb_zone": "BombsiteA"},
                ],
            },
            "ticks": [
                {"round_num": 1, "tick": 0, "team_name": "CT", "health": 100, "steamid": "ct1"},
                {"round_num": 1, "tick": 0, "team_name": "T", "health": 100, "steamid": "t1"},
                {"round_num": 1, "tick": 10, "team_name": "CT", "health": 100, "steamid": "ct1"},
                {"round_num": 1, "tick": 10, "team_name": "T", "health": 0, "steamid": "t1"},
                {"round_num": 1, "tick": 15, "team_name": "CT", "health": 100, "steamid": "ct1"},
                {"round_num": 1, "tick": 15, "team_name": "T", "health": 0, "steamid": "t1"},
                {"round_num": 2, "tick": 20, "team_name": "CT", "health": 100, "steamid": "ct1"},
                {"round_num": 2, "tick": 20, "team_name": "T", "health": 100, "steamid": "t1"},
            ],
        }

    def test_report_contains_timeline_swings_and_event_annotations(self) -> None:
        report = build_full_match_report(self._record(), _DeterministicPredictor())
        self.assertEqual(report["report_type"], "full_match_timeline")
        self.assertEqual(report["timeline_points"], 4)
        self.assertEqual(report["tick_rate"], 10.0)
        self.assertEqual(report["event_counts"], {"bomb": 1, "death": 1, "kill": 1})
        self.assertEqual(report["timeline"][1]["probability_swing"]["direction"], "ct_gain")
        self.assertEqual(report["timeline"][1]["events"][0]["category"], "kill")
        self.assertEqual(report["timeline"][2]["events"][0]["category"], "bomb")
        # A new round starts a new probability baseline, so no cross-round
        # swing is reported at tick 20.
        self.assertIsNone(report["timeline"][3]["probability_swing"])

    def test_report_is_deterministic_and_limits_top_swings(self) -> None:
        first = build_full_match_report(self._record(), ensemble=_DeterministicPredictor(), top_swing_count=1)
        second = build_full_match_report(self._record(), _DeterministicPredictor(), top_swing_count=1)
        self.assertEqual(first, second)
        self.assertEqual(len(first["probability_swings"]), 1)
        self.assertEqual(first["events"][0]["event_id"], "event-000001")


if __name__ == "__main__":
    unittest.main()
