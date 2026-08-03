import unittest

from Noah.training.bayesian_decisions import (
    BetaPosterior,
    compare_action_counts,
    compare_beta_actions,
    compare_posteriors,
    posterior_from_probability,
)


class BayesianDecisionTests(unittest.TestCase):
    def test_beta_posterior_updates_mean_and_variance(self):
        posterior = BetaPosterior(8, 2)
        self.assertAlmostEqual(posterior.alpha, 9.0)
        self.assertAlmostEqual(posterior.beta, 3.0)
        self.assertAlmostEqual(posterior.mean, 0.75)
        self.assertGreater(posterior.variance, 0.0)
        self.assertEqual(posterior.support, 10)

    def test_strong_alternative_has_high_probability_and_positive_regret(self):
        report = compare_action_counts(10, 90, 90, 10, samples=5_000, seed=7)
        self.assertEqual(report["schema_version"], "bayesian_action_decision_v1")
        self.assertGreater(report["probability_alternative_beats_by_epsilon"], 0.99)
        self.assertGreater(report["expected_regret"], 0.5)
        self.assertGreater(report["difference_credible_interval"][0], 0.5)
        self.assertEqual(report["monte_carlo_samples"], 5_000)

    def test_epsilon_reduces_probability_and_equal_posteriors_are_symmetric(self):
        baseline = compare_action_counts(50, 50, 50, 50, samples=5_000, seed=11)
        margin = compare_action_counts(50, 50, 50, 50, epsilon=0.2, samples=5_000, seed=11)
        self.assertAlmostEqual(baseline["probability_alternative_beats_observed"], 0.5, delta=0.04)
        self.assertLess(margin["probability_alternative_beats_observed"], baseline["probability_alternative_beats_observed"])
        self.assertGreaterEqual(margin["expected_regret_after_epsilon"], 0.0)

    def test_probability_adapter_and_direct_comparison_are_json_friendly(self):
        observed = posterior_from_probability(0.4, 20)
        alternative = posterior_from_probability(0.7, 20)
        report = compare_posteriors(observed, alternative, samples=2_000, seed=3)
        self.assertGreater(report["probability_alternative_better"], 0.9)
        self.assertEqual(report["observed"]["support"], 20.0)
        self.assertEqual(len(report["alternative_credible_interval"]), 2)
        self.assertIsInstance(compare_beta_actions({"wins": 1, "losses": 1}, {"wins": 2, "losses": 0}, samples=100), dict)

    def test_invalid_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            BetaPosterior(-1, 0)
        with self.assertRaises(ValueError):
            posterior_from_probability(1.1, 10)
        with self.assertRaises(ValueError):
            compare_action_counts(1, 1, 1, 1, epsilon=1.0)
        with self.assertRaises(ValueError):
            compare_action_counts(1, 1, 1, 1, samples=0)


if __name__ == "__main__":
    unittest.main()

