import unittest

from cs2_sim.core.model import SmallStatisticalModel
from cs2_sim.rules import legal_actions

from Noah.training.analysis_harness import (
    HarnessConfig,
    build_replay_analysis,
    reconstruct_game_state,
)
from Noah.training.replay_state import bomb_state


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


class _MultiKillReportModel:
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
                    "probability_swing": {"delta": -0.2, "absolute": 0.2},
                    "events": [
                        {
                            "event_id": "event-1",
                            "category": "kill",
                            "attacker_id": "ct1",
                            "victim_id": "t1",
                            "round_num": 1,
                            "tick": 10,
                        },
                        {
                            "event_id": "event-2",
                            "category": "kill",
                            "attacker_id": "ct2",
                            "victim_id": "t2",
                            "round_num": 1,
                            "tick": 10,
                        },
                    ],
                }
            ],
        }


class _EngagementReportModel:
    def analyse_match(self, replay, **kwargs):
        return {
            "report_type": "full_match_timeline",
            "source": "engagement.dem",
            "map_name": "de_mirage",
            "event_counts": {"kill": 1},
            "timeline": [
                {
                    "round_num": 1,
                    "tick": 128,
                    "probability_ct_win": 0.4,
                    "probability_swing": {"delta": -0.2, "absolute": 0.2},
                    "events": [
                        {
                            "event_id": "kill-1",
                            "category": "kill",
                            "attacker_id": "ct1",
                            "victim_id": "t1",
                            "round_num": 1,
                            "tick": 110,
                        }
                    ],
                }
            ],
        }

    def score_engagement(self, row):
        move = row.get("observed_action") == "move"
        return {
            "kill_probability": 0.35 if move else 0.20,
            "death_probability": 0.25 if move else 0.70,
            "trade_probability": 0.10,
            "survival_probability": 0.75 if move else 0.30,
            "damage_probability": 0.60 if move else 0.30,
            "round_win_probability": 0.65 if move else 0.35,
            "sample_count": 20,
            "confidence": 0.9,
            "entropy": 0.5,
            "supported": True,
            "state_key": f"test|{row.get('observed_action')}",
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
        self.assertEqual(report["moments"][0]["probability_decision_class"], "insufficient_evidence")
        self.assertEqual(report["summary"]["probability_decision_classes"], {"insufficient_evidence": 1})

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
        self.assertIsNotNone(moment["least_death_risk_action"])
        self.assertIn("action", moment["least_death_risk_action"])
        self.assertIn("death_probability", moment["least_death_risk_action"])
        self.assertIn("risk_upper_bound", moment["least_death_risk_action"])
        self.assertEqual(
            report["summary"]["least_risk_fallback_count"],
            0,
        )
        self.assertEqual(report["summary"]["least_risk_candidate_count"], 1)
        self.assertEqual(report["summary"]["least_risk_usable_count"], 1)
        self.assertEqual(len(moment["candidate_actions"]), moment["legal_candidate_count"])
        self.assertIn("posterior_successes", moment["best_estimated_alternative"])
        self.assertTrue(moment["best_estimated_alternative"]["legal"])
        self.assertGreaterEqual(moment["best_estimated_alternative"]["entropy"], 0.0)
        self.assertLessEqual(moment["best_estimated_alternative"]["entropy"], 1.0)

    def test_rubric_candidate_model_does_not_become_death_risk(self):
        record = self._record()
        state = reconstruct_game_state(record, round_num=1, tick=10)
        self.assertIsNotNone(state)
        model = SmallStatisticalModel()
        model.training_target = "pre_event_suitability"
        for action in legal_actions(state, "ct1"):
            model.observe(state, "ct1", action, success=action.action_type.value == "hold")
        report = build_replay_analysis(
            record,
            _ReportModel(),
            candidate_model=model,
            config=HarnessConfig(sample_every=1),
        )
        moment = report["moments"][0]
        self.assertEqual(moment["candidate_source"], "rubric_action_suitability")
        self.assertEqual(moment["candidate_model_type"], "small_statistical_rubric_suitability")
        self.assertEqual(
            moment["best_estimated_alternative"]["estimate_type"],
            "rubric_action_suitability",
        )
        self.assertEqual(moment["least_death_risk_action"], None)

    def test_simultaneous_kills_keep_actor_specific_context(self):
        record = self._record()
        record["ticks"].extend(
            [
                {"round_num": 1, "tick": 0, "steamid": "ct2", "side": "ct", "health": 100, "place": "A_SITE"},
                {"round_num": 1, "tick": 0, "steamid": "t2", "side": "t", "health": 100, "place": "A_MAIN"},
            ]
        )
        report = build_replay_analysis(
            record,
            _MultiKillReportModel(),
            config=HarnessConfig(sample_every=1),
        )
        self.assertEqual(report["summary"]["moment_count"], 2)
        self.assertEqual(
            [item["actor_id"] for item in report["moments"]],
            ["t1", "t2"],
        )
        self.assertEqual(report["summary"]["kill_analysis_count"], 2)
        self.assertEqual(
            [row["attacker_id"] for row in report["kill_analysis"]],
            ["ct1", "ct2"],
        )

    def test_engagement_heads_rank_high_level_observed_action(self):
        record = self._record()
        record["damages"] = [
            {
                "round_num": 1,
                "tick": 100,
                "attacker_steamid": "ct1",
                "victim_steamid": "t1",
                "attacker_side": "ct",
                "victim_side": "t",
                "weapon": "m4a1",
                "dmg_health_real": 25,
            }
        ]
        record["kills"] = [
            {
                "round_num": 1,
                "tick": 110,
                "attacker_steamid": "ct1",
                "victim_steamid": "t1",
                "attacker_side": "ct",
                "victim_side": "t",
                "weapon": "m4a1",
            }
        ]
        record["ticks"].extend(
            [
                {"round_num": 1, "tick": 36, "steamid": "t1", "side": "t", "health": 100, "place": "A_MAIN", "X": 0, "Y": 0},
                {"round_num": 1, "tick": 100, "steamid": "t1", "side": "t", "health": 75, "place": "A_SITE", "X": 100, "Y": 0},
            ]
        )
        report = build_replay_analysis(
            record,
            _EngagementReportModel(),
            config=HarnessConfig(sample_every=1),
        )
        moment = report["moments"][0]
        self.assertEqual(moment["actor_id"], "t1")
        self.assertEqual(moment["decision_tick"], 36)
        self.assertEqual(moment["best_estimated_alternative"]["action"], "move")
        self.assertEqual(moment["observed_action_name"], "move_to_adjacent_zone:A_SITE")
        self.assertEqual(moment["probability_decision_class"], "good")
        self.assertEqual(moment["best_estimated_alternative"]["death_probability_source"], "engagement_death_head")

    def test_candidate_state_can_exclude_same_tick_kill_outcome(self):
        record = self._record()
        record["ticks"].extend(
            [
                {"round_num": 1, "tick": 10, "steamid": "ct1", "side": "ct", "health": 100},
                {"round_num": 1, "tick": 10, "steamid": "t1", "side": "t", "health": 0, "alive": False},
            ]
        )

        after_event = reconstruct_game_state(record, round_num=1, tick=10)
        before_event = reconstruct_game_state(record, round_num=1, tick=10, before_event=True)

        self.assertIsNotNone(after_event)
        self.assertIsNotNone(before_event)
        self.assertFalse(after_event.players["t1"].alive)
        self.assertTrue(before_event.players["t1"].alive)

    def test_candidate_state_uses_elapsed_round_time(self):
        state = reconstruct_game_state(self._record(), round_num=1, tick=128)
        self.assertIsNotNone(state)
        self.assertEqual(state.time_seconds, 2.0)

    def test_constant_candidate_outcomes_abstain(self):
        record = self._record()
        state = reconstruct_game_state(record, round_num=1, tick=10)
        self.assertIsNotNone(state)
        model = SmallStatisticalModel()
        for action in legal_actions(state, "ct1"):
            for _ in range(10):
                model.observe(state, "ct1", action, success=True)
        report = build_replay_analysis(
            record,
            _ReportModel(),
            candidate_model=model,
            config=HarnessConfig(sample_every=1),
        )
        moment = report["moments"][0]
        self.assertEqual(moment["probability_decision_class"], "insufficient_evidence")
        self.assertEqual(
            moment["probability_abstention"]["reason"],
            "no_counterfactual_outcome_variance",
        )
        self.assertEqual(
            moment["least_death_risk_action"]["fallback_status"],
            "abstained_no_action_outcome_variance",
        )
        self.assertFalse(moment["least_death_risk_action"]["fallback_usable"])

    def test_before_event_without_prior_snapshot_abstains(self):
        record = self._record()
        record["ticks"] = [row for row in record["ticks"] if row["tick"] == 10]
        self.assertIsNone(
            reconstruct_game_state(record, round_num=1, tick=10, before_event=True)
        )

    def test_before_event_excludes_same_tick_bomb_and_uses_elapsed_timer(self):
        record = {
            "header": {"tick_rate": 64},
            "rounds": [{"round_num": 1, "start": 0, "end": 1000}],
            "bomb": [
                {"round_num": 1, "tick": 100, "event": "bomb_planted", "bombsite": "B"},
            ],
            "ticks": [
                {
                    "round_num": 1,
                    "tick": 90,
                    "steamid": "t1",
                    "team_name": "T",
                    "health": 100,
                    "place": "B_SITE",
                    "has_bomb": True,
                },
                {
                    "round_num": 1,
                    "tick": 100,
                    "steamid": "t1",
                    "team_name": "T",
                    "health": 100,
                    "place": "B_SITE",
                    "has_bomb": True,
                },
            ],
        }

        before = reconstruct_game_state(record, round_num=1, tick=100, before_event=True)
        self.assertIsNotNone(before)
        self.assertEqual(before.bomb_state.value, "none")
        self.assertEqual(before.bomb_site, "UNKNOWN_SITE")
        self.assertIsNone(before.bomb_time_remaining)

        after = reconstruct_game_state(record, round_num=1, tick=228)
        self.assertIsNotNone(after)
        self.assertEqual(after.bomb_state.value, "planted")
        self.assertEqual(after.bomb_site, "B_SITE")
        self.assertAlmostEqual(after.bomb_time_remaining or 0.0, 38.0)

        self.assertEqual(
            bomb_state(record, round_num=1, tick=100, strict_before=True),
            (before.bomb_state, before.bomb_site, before.bomb_time_remaining),
        )


if __name__ == "__main__":
    unittest.main()
