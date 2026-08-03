from dataclasses import dataclass
from copy import deepcopy

from .actions import Action, ActionExecution, ActionType, action_duration
from .config import SimConfig
from .events import Event
from .policy import ActionPolicy
from .rules import legal_actions, round_winner
from .state import BombState, GameState, Team


@dataclass(frozen=True, slots=True)
class SimulationResult:
    final_state: GameState
    events: tuple[Event, ...]
    winner: Team | None


class Simulator:
    def __init__(self, config: SimConfig, policy: ActionPolicy) -> None:
        self.config = config
        self.policy = policy

    def run(self, state: GameState) -> SimulationResult:
        state = deepcopy(state)
        executions: dict[str, ActionExecution] = {}
        events: list[Event] = []
        next_decision = 0.0

        while state.winner is None and state.time_seconds < self.config.round_time_seconds + self.config.bomb_time_seconds:
            if state.time_seconds + 1e-9 >= next_decision:
                self._choose_actions(state, executions, events)
                next_decision += self.config.decision_interval_seconds

            self._advance_actions(state, executions, events)
            state.time_seconds += self.config.tick_seconds
            if state.bomb_time_remaining is not None:
                state.bomb_time_remaining -= self.config.tick_seconds
                if state.bomb_time_remaining <= 0 and state.bomb_state is BombState.PLANTED:
                    state.bomb_state = BombState.DETONATED
                    self._record(events, state, "bomb_detonated")

            state.winner = round_winner(state, self.config)

        return SimulationResult(state, tuple(events), state.winner)

    def _choose_actions(
        self,
        state: GameState,
        executions: dict[str, ActionExecution],
        events: list[Event],
    ) -> None:
        for player in state.alive_players():
            if player.player_id in executions:
                continue
            legal = legal_actions(state, player.player_id)
            if not legal:
                continue
            action = self.policy.choose_action(state, player.player_id, legal)
            if action not in legal:
                raise ValueError(f"policy selected illegal action: {action}")
            executions[player.player_id] = ActionExecution(
                action,
                starting_health=player.health,
            )
            self._record(events, state, "action_started", player.player_id, action=action.action_type.value)

    def _advance_actions(
        self,
        state: GameState,
        executions: dict[str, ActionExecution],
        events: list[Event],
    ) -> None:
        completed: list[str] = []
        for player_id, execution in executions.items():
            player = state.player(player_id)
            if self._should_interrupt(state, player_id, execution):
                self._record(
                    events,
                    state,
                    "action_interrupted",
                    player_id,
                    action=execution.action.action_type.value,
                )
                completed.append(player_id)
                continue
            action_remaining = action_duration(execution.action, self.config) - execution.elapsed_seconds
            if (
                execution.action.action_type is ActionType.DEFUSE
                and state.bomb_state is BombState.PLANTED
                and state.bomb_time_remaining is not None
                and action_remaining > state.bomb_time_remaining
            ):
                execution.elapsed_seconds += min(
                    self.config.tick_seconds,
                    max(0.0, state.bomb_time_remaining),
                )
                continue
            execution.elapsed_seconds += self.config.tick_seconds
            if execution.elapsed_seconds + 1e-9 >= action_duration(execution.action, self.config):
                self._complete_action(state, execution.action, player_id, events)
                completed.append(player_id)
        for player_id in completed:
            del executions[player_id]

    @staticmethod
    def _should_interrupt(
        state: GameState,
        player_id: str,
        execution: ActionExecution,
    ) -> bool:
        player = state.player(player_id)
        if not player.alive:
            return True
        if execution.starting_health is not None and player.health < execution.starting_health:
            return True
        return bool(
            player.visible_enemies
            and execution.action.action_type
            in {
                ActionType.MOVE_TO_ADJACENT_ZONE,
                ActionType.USE_UTILITY,
                ActionType.SAVE,
            }
        )

    def _complete_action(
        self,
        state: GameState,
        action: Action,
        player_id: str,
        events: list[Event],
    ) -> None:
        player = state.player(player_id)
        if action.action_type is ActionType.MOVE_TO_ADJACENT_ZONE:
            if action.target_zone is None:
                raise ValueError("move action needs a target zone")
            player.zone = action.target_zone
        elif action.action_type is ActionType.USE_UTILITY:
            player.utility_count = max(0, player.utility_count - 1)
        elif action.action_type is ActionType.PLANT:
            state.bomb_state = BombState.PLANTED
            state.bomb_time_remaining = self.config.bomb_time_seconds
            player.has_bomb = False
            state.bomb_carrier = None
        elif action.action_type is ActionType.DEFUSE:
            if state.bomb_state is not BombState.PLANTED or player.zone != state.bomb_site:
                self._record(events, state, "action_rejected", player_id, action=action.action_type.value)
                return
            state.bomb_state = BombState.DEFUSED
            state.bomb_time_remaining = None
        self._record(events, state, "action_completed", player_id, action=action.action_type.value)

    @staticmethod
    def _record(
        events: list[Event],
        state: GameState,
        kind: str,
        player_id: str | None = None,
        **details: str | float | int,
    ) -> None:
        events.append(Event(state.time_seconds, kind, player_id, details))
