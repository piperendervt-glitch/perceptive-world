import copy

import pytest

from trpg_core.input_actions import MovePlayerToPositionAction
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import GameState
from trpg_core.spatial import PlayerPosition
from trpg_core.spatial_actions import apply_player_movement
from trpg_core.world import location_world_object_id


def _well_state(position=PlayerPosition(1, 2)):
    state = GameState(7, scenario=load_scenario("goblin"))
    state.transition_location("well")
    state.player_position = position
    return state


def _fingerprint(state):
    return (copy.deepcopy(state.snapshot()), state.player_position, state.focus_state,
            state.lod_runtime, state.rng.state(), copy.deepcopy(state.log))


def test_game_state_owns_optional_exact_independent_position():
    one = GameState(1, scenario=load_scenario("goblin"))
    two = GameState(2, scenario=load_scenario("goblin"))
    assert one.player_position == two.player_position == PlayerPosition(3, 2)
    one.player_position = PlayerPosition(1, 2)
    assert two.player_position == PlayerPosition(3, 2)
    assert one.location != one.player_position
    for invalid in ((1, 2), {"x": 1, "y": 2}, [1, 2]):
        with pytest.raises(ValueError):
            one.player_position = invalid


def test_valid_headless_move_changes_only_position():
    state = _well_state()
    focused = location_world_object_id("goblin", "well")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    before = _fingerprint(state)
    apply_player_movement(state, MovePlayerToPositionAction(PlayerPosition(2, 2)))
    after = _fingerprint(state)
    assert state.player_position == PlayerPosition(2, 2)
    assert after[:1] + after[2:] == before[:1] + before[2:]


@pytest.mark.parametrize("state,action", [
    (GameState(7, scenario=load_scenario("goblin")), MovePlayerToPositionAction(PlayerPosition(1, 2))),
    (_well_state(None), MovePlayerToPositionAction(PlayerPosition(2, 2))),
    (_well_state(), MovePlayerToPositionAction(PlayerPosition(1, 2))),
    (_well_state(), MovePlayerToPositionAction(PlayerPosition(2, 3))),
    (_well_state(), MovePlayerToPositionAction(PlayerPosition(3, 2))),
    (_well_state(PlayerPosition(2, 2)), MovePlayerToPositionAction(PlayerPosition(3, 2))),
    (_well_state(PlayerPosition(0, 0)), MovePlayerToPositionAction(PlayerPosition(1, 0))),
])
def test_invalid_movement_is_atomic(state, action):
    before = _fingerprint(state)
    with pytest.raises(ValueError):
        apply_player_movement(state, action)
    assert _fingerprint(state) == before


def test_movement_rejects_malformed_action_without_state_change():
    state = _well_state()
    before = _fingerprint(state)
    with pytest.raises(ValueError):
        apply_player_movement(state, PlayerPosition(2, 2))
    assert _fingerprint(state) == before


def test_direct_movement_to_exit_cell_is_atomic():
    state = GameState(7, scenario=load_scenario("goblin"))
    state.player_position = PlayerPosition(3, 1)
    before = _fingerprint(state)
    with pytest.raises(ValueError, match="exit cell"):
        apply_player_movement(
            state, MovePlayerToPositionAction(PlayerPosition(3, 0)),
        )
    assert _fingerprint(state) == before
