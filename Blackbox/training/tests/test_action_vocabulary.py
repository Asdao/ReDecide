import unittest

from cs2_sim.action_vocabulary import (
    ACTION_FEATURE_NAMES,
    action_features,
    action_parameters,
    canonical_action,
)
from Blackbox.training.action_labeler import classify_action


class ActionVocabularyTests(unittest.TestCase):
    def test_aliases_and_parameters_are_canonical(self):
        self.assertEqual(canonical_action("move_to_adjacent_zone:A_SITE"), "move_to_adjacent_zone")
        self.assertEqual(canonical_action("reposition"), "move_to_adjacent_zone")
        self.assertEqual(
            action_parameters("move_to_adjacent_zone:A_SITE"),
            {"target_zone": "A_SITE"},
        )

    def test_one_hot_encoding_does_not_use_ordinal_action_codes(self):
        features = action_features("peek")
        self.assertEqual(set(features), set(ACTION_FEATURE_NAMES))
        self.assertEqual(sum(features.values()), 1.0)
        self.assertEqual(features["action_is_peek"], 1.0)

    def test_exact_utility_and_objective_events_win_over_movement(self):
        record = {
            "events": {
                "weapon_fire": [
                    {
                        "round_num": 1,
                        "tick": 15,
                        "steamid": "p1",
                        "weapon": "smokegrenade",
                    }
                ]
            },
            "bomb": [
                {"round_num": 1, "tick": 16, "steamid": "p1", "event": "bomb_planted"}
            ],
        }
        utility = classify_action(
            record,
            player_id="p1",
            round_num=1,
            decision_tick=10,
            action_end_tick=15,
            tick_series=[],
            tick_rate=64,
        )
        self.assertEqual(utility["action"], "use_utility")
        objective = classify_action(
            record,
            player_id="p1",
            round_num=1,
            decision_tick=10,
            action_end_tick=16,
            tick_series=[],
            tick_rate=64,
        )
        self.assertEqual(objective["action"], "plant")

    def test_movement_is_peek_only_for_contact_initiator(self):
        series = [
            {"tick": 10, "X": 0, "Y": 0, "place": "A_MAIN"},
            {"tick": 20, "X": 50, "Y": 0, "place": "A_SITE"},
        ]
        peek = classify_action(
            {},
            player_id="p1",
            round_num=1,
            decision_tick=10,
            action_end_tick=20,
            tick_series=series,
            tick_rate=10,
            contact_actor="p1",
        )
        self.assertEqual(peek["action"], "peek")
        reposition = classify_action(
            {},
            player_id="p1",
            round_num=1,
            decision_tick=10,
            action_end_tick=20,
            tick_series=series,
            tick_rate=10,
            contact_actor="enemy",
        )
        self.assertEqual(reposition["action"], "move_to_adjacent_zone")


if __name__ == "__main__":
    unittest.main()
