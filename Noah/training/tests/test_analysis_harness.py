import unittest

from cs2_sim.core.model import SmallStatisticalModel
from cs2_sim.rules import legal_actions

from Noah.training.analysis_harness import (
    HarnessConfig,
    build_replay_analysis,
    reconstruct_game_state,
)


class _ReportModel:
    def analyse_match(self, replay, **kwargs):
        return {
            "report_type": "full_match_timeline",
            "source": "fixture.dem",
            "map_name": "de_mirage",
            "timeline": [
                {
                    "round_num": 1,
                    "tick": 10,
                    "probability_ct_win": 0.3,
                    "probability_swing": {
                        "delta": -0.2,
                        "absolute": 0.2,
                        "direction": "t_gain",
                    },
                    "events": [
                        {
                            "event_id": "event-1",
                            "category": "death",
                            "actor_id": "ct1",
                            "round_num": 1,
                            "tick": 10,
                        }
                    ],
                }
            ],
        }


class AnalysisHarnessTests(unittest.TestCase):
    def _record(self):
        return {
            "demo_file": "fixture.dem",
            "header": {"map_name": "de_mirage", "tick_rate": 64},
            "rounds": [{"round_num": 1, "start": 0, "end": 200, "winner": "t"}],
            "kills": [],
            "damages": [],
            "bomb": [],
            "ticks": [
                {"round_num": 1, "tick": 0, "steamid": "ct1", "side": "ct", "health": 100, "place": "A_SITE", "X": 0, "Y": 0},
                {"round_num": 1, "tick": 0, "steamid": "t1", "side": "t", "health": 100, "place": "A_MAIN", "X": 0, "Y": 0},
                {"round_num": 1, "tick": 128, "steamid": "ct1", "side": "ct", "health": 100, "place": "A_SITE", "X": 0, "Y": 0},
                {"round_num": 1, "tick": 128, "steamid": "t1", "side": "t", "health": 100, "place": "A_MAIN", "X": 0, "Y": 0},
            ],
        }

    def test_key_moment_is_reported_without_candidate_model(self):
        report = build_replay_analysis(
            self._record(),
            _ReportModel(),
            config=HarnessConfig(sample_every=1),
        )
        self.assertEqual(report["report_type"], "combined_replay_analysis")
        self.assertEqual(report["summary"]["moment_count"], 1)
        self.assertEqual(report["moments"][0]["decision_class"], "no_observed_action")
        self.assertEqual(report["moments"][0]["candidate_source"], "unavailable")

    def test_candidate_model_scores_only_reconstructed_legal_actions(self):
        record = self._record()
        state = reconstruct_game_state(record, round_num=1, tick=10)
        self.assertIsNotNone(state)
        self.assertEqual(state.players["ct1"].zone, "A_SITE")
        model = SmallStatisticalModel()
        legal = legal_actions(state, "ct1")
        for action in legal:
            model.observe(state, "ct1", action, success=action.action_type.value == "hold")
            if action.action_type.value == "hold":
                for _ in range(10):
                    model.observe(state, "ct1", action, success=True)
        report = build_replay_analysis(
            record,
            _ReportModel(),
            candidate_model=model,
            config=HarnessConfig(sample_every=1),
        )
        moment = report["moments"][0]
        self.assertEqual(moment["candidate_source"], "simulator_action_value")
        self.assertEqual(moment["candidate_model_type"], "small_statistical")
        self.assertGreater(moment["legal_candidate_count"], 0)
        self.assertEqual(moment["best_estimated_alternative"]["action"], "hold")
        self.assertEqual(moment["best_estimated_alternative"]["estimate_type"], "simulator_action_value_estimate")
        self.assertEqual(len(moment["candidate_actions"]), moment["legal_candidate_count"])
        self.assertTrue(moment["best_estimated_alternative"]["legal"])


if __name__ == "__main__":
    unittest.main()
