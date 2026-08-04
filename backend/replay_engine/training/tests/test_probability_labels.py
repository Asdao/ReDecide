import unittest
from pathlib import Path
from unittest.mock import patch

from cs2_sim import ReplayModel
from cs2_sim.core.model import ReplayValueEnsemble

from backend.replay_engine.training.recommendations import (
    ProbabilityLabelThresholds,
    annotate_probability_labels,
)


class ProbabilityLabelTests(unittest.TestCase):
    def _report(self):
        return {
            "report_type": "combined_replay_analysis",
            "moments": [
                {
                    "round_num": 1,
                    "tick": 10,
                    "candidate_actions": [
                        {
                            "action": "hold",
                            "candidate_success_probability": 0.85,
                            "sample_count": 30,
                            "posterior_successes": 26,
                            "posterior_failures": 4,
                            "outcome_evidence": True,
                            "outcome_variance": True,
                        },
                        {
                            "action": "peek",
                            "candidate_success_probability": 0.45,
                            "sample_count": 30,
                            "posterior_successes": 10,
                            "posterior_failures": 20,
                            "outcome_evidence": True,
                            "outcome_variance": True,
                        },
                    ],
                    "best_estimated_alternative": {
                        "action": "hold",
                        "candidate_success_probability": 0.85,
                        "sample_count": 30,
                        "posterior_successes": 26,
                        "posterior_failures": 4,
                        "outcome_evidence": True,
                        "outcome_variance": True,
                    },
                    "observed_action": {
                        "action": "peek",
                        "candidate_success_probability": 0.45,
                        "sample_count": 30,
                        "posterior_successes": 10,
                        "posterior_failures": 20,
                        "outcome_evidence": True,
                        "outcome_variance": True,
                    },
                    "decision_class": "bad",
                },
                {
                    "round_num": 1,
                    "tick": 20,
                    "candidate_actions": [
                        {"action": "hold", "candidate_success_probability": 0.60, "sample_count": 1},
                    ],
                    "best_estimated_alternative": {
                        "action": "hold",
                        "candidate_success_probability": 0.60,
                        "sample_count": 1,
                    },
                    "observed_action": {
                        "action": "hold",
                        "candidate_success_probability": 0.60,
                        "sample_count": 1,
                    },
                    "decision_class": "good",
                },
            ],
            "summary": {"moment_count": 2},
        }

    def test_probability_label_is_conservative_and_additive(self):
        report = self._report()
        labelled = annotate_probability_labels(report)
        first, second = labelled["moments"]
        self.assertEqual(first["probability_decision_class"], "bad")
        self.assertGreater(first["probability_of_improvement"], 0.8)
        self.assertGreater(first["expected_regret"], 0.0)
        self.assertEqual(first["credible_intervals"]["observed_action"]["level"], 0.9)
        self.assertEqual(first["credible_intervals"]["observed_action"]["method"], "beta_normal_approximation")
        self.assertEqual(second["probability_decision_class"], "insufficient_evidence")
        self.assertTrue(second["probability_abstention"]["abstained"])
        self.assertEqual(second["probability_abstention"]["reason"], "support_below_threshold")
        self.assertEqual(first["decision_class"], "bad")
        self.assertEqual(labelled["probability_label_schema_version"], "probability_labels_v1")

    def test_thresholds_and_posterior_counts_are_validated(self):
        with self.assertRaises(ValueError):
            ProbabilityLabelThresholds(probability_of_improvement=0.5)
        custom = ProbabilityLabelThresholds(min_support=0, credible_level=0.95)
        report = self._report()
        report["moments"][0]["candidate_actions"][0].update({"posterior_successes": 9, "posterior_failures": 1})
        labelled = annotate_probability_labels(report, thresholds=custom)
        interval = labelled["moments"][0]["candidate_actions"][0]["credible_interval"]
        self.assertEqual(interval["method"], "beta_normal_approximation")
        self.assertEqual(interval["observations"], 10)
        self.assertEqual(labelled["config"]["probability_thresholds"]["credible_level"], 0.95)

    def test_proxy_probability_without_outcome_counts_abstains(self):
        report = self._report()
        for moment in report["moments"][:1]:
            for candidate in (moment["candidate_actions"] + [moment["best_estimated_alternative"], moment["observed_action"]]):
                candidate.pop("posterior_successes", None)
                candidate.pop("posterior_failures", None)
                candidate.pop("outcome_evidence", None)
                candidate.pop("outcome_variance", None)
        labelled = annotate_probability_labels(report)
        first = labelled["moments"][0]
        self.assertEqual(first["probability_decision_class"], "insufficient_evidence")
        self.assertEqual(first["probability_abstention"]["reason"], "outcome_support_missing")

    def test_public_api_adds_probability_contract_without_removing_legacy_fields(self):
        model = ReplayModel(
            ReplayValueEnsemble(),
            release_path=Path("."),
            manifest_path=Path("manifest.json"),
        )
        legacy = {
            "report_type": "combined_replay_analysis",
            "moments": [
                {
                    "decision_class": "bad",
                    "candidate_actions": [],
                    "best_estimated_alternative": None,
                    "observed_action": None,
                }
            ],
            "summary": {},
        }
        with patch("backend.replay_engine.training.analysis_harness.build_replay_analysis", return_value=legacy):
            report = model.analyse_replay({}, probability_of_improvement_threshold=0.85)
        self.assertEqual(report["moments"][0]["decision_class"], "bad")
        self.assertEqual(report["moments"][0]["probability_decision_class"], "insufficient_evidence")
        self.assertEqual(report["config"]["probability_thresholds"]["probability_of_improvement"], 0.85)


if __name__ == "__main__":
    unittest.main()
