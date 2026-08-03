import unittest
from tempfile import TemporaryDirectory

from cs2_sim.actions import Action, ActionType
from cs2_sim.bayesian_policy import BayesianPolicy
from cs2_sim.state import BombState, GameState, PlayerState, Team


class PolicyTests(unittest.TestCase):
    def test_bayesian_policy_only_selects_legal_actions(self) -> None:
        state = GameState({"t1": PlayerState("t1", Team.T, "MID")}, BombState.CARRIED)
        legal = (Action(ActionType.HOLD), Action(ActionType.PEEK))
        policy = BayesianPolicy(seed=4)
        for _ in range(20):
            self.assertIn(policy.choose_action(state, "t1", legal), legal)

    def test_policy_round_trip(self) -> None:
        state = GameState({"t1": PlayerState("t1", Team.T, "MID")}, BombState.CARRIED)
        policy = BayesianPolicy(seed=4)
        policy.observe(state, "t1", ActionType.PEEK)
        with TemporaryDirectory() as directory:
            path = f"{directory}/model.json"
            policy.save(path)
            loaded = BayesianPolicy.load(path, seed=4)
        self.assertEqual(loaded._counts, policy._counts)

    def test_bayesian_policy_preserves_move_destination(self) -> None:
        state = GameState({"t1": PlayerState("t1", Team.T, "MID")}, BombState.CARRIED)
        policy = BayesianPolicy(seed=4)
        policy.observe(state, "t1", Action(ActionType.MOVE_TO_ADJACENT_ZONE, "A_SITE"))
        key = policy.state_key(state, "t1")
        self.assertEqual(policy._counts[key]["move_to_adjacent_zone:A_SITE"], 1)
