import unittest

from Blackbox.training.recommendations import rank_candidate_actions


class RecommendationTests(unittest.TestCase):
    def test_supported_higher_value_candidate_is_ranked_first(self):
        result = rank_candidate_actions(
            [
                {"action": "wide_peek", "death_probability": 0.68, "round_value_delta": -0.14, "sample_count": 20, "entropy": 0.4},
                {"action": "hold_connector", "death_probability": 0.31, "round_value_delta": 0.03, "sample_count": 20, "entropy": 0.4},
            ]
        )
        self.assertEqual([row["action"] for row in result], ["hold_connector", "wide_peek"])
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[0]["estimate_type"], "observational_counterfactual_estimate")

    def test_order_is_stable_and_duplicates_are_rejected(self):
        result = rank_candidate_actions(
            [{"action": "b"}, {"action": "a"}], min_support=1
        )
        self.assertEqual([row["action"] for row in result], ["a", "b"])
        with self.assertRaises(ValueError):
            rank_candidate_actions([{"action": "a"}, {"action": "a"}])


if __name__ == "__main__":
    unittest.main()
