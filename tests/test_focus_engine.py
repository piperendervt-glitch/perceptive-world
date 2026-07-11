"""FocusStateのengine runtime接続とscene遷移回帰。"""

from __future__ import annotations

import copy
import builtins
import os

import pytest

from trpg_core.map import build_map
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import ConsoleController, GameState, _goto
from trpg_core.world import FocusState, WorldObjectId


def _state(seed=7):
    return GameState(seed, scenario=load_scenario("goblin"))


def _id(local="location/well"):
    return WorldObjectId("goblin", local)


def _fingerprint(state):
    return {
        "snapshot": copy.deepcopy(state.snapshot()),
        "rng": state.rng.state(),
        "log": copy.deepcopy(state.log),
    }


def test_game_states_own_distinct_default_focus_states():
    one = _state()
    two = _state()
    assert isinstance(one.focus_state, FocusState)
    assert one.focus_state.focused_object_id is None
    assert two.focus_state.focused_object_id is None
    assert one.focus_state is not two.focus_state


def test_valid_focus_setting_delegates_to_world_model_without_side_effects():
    state = _state()
    object_id = _id()
    before = _fingerprint(state)
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    assert state.focus_state.focused_object_id is object_id
    assert _fingerprint(state) == before


def test_invalid_focus_is_rejected_without_changing_any_state():
    state = _state()
    current = _id("location/plaza")
    rejected = _id()
    state.set_focused_object(current, focusable_object_ids=(current,))
    focus_before = state.focus_state
    before = _fingerprint(state)
    with pytest.raises(ValueError):
        state.set_focused_object(rejected, focusable_object_ids=(current,))
    assert state.focus_state is focus_before
    assert _fingerprint(state) == before


def test_refocusing_same_object_is_idempotent():
    state = _state()
    object_id = _id()
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    focus_before = state.focus_state
    before = _fingerprint(state)
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    assert state.focus_state is focus_before
    assert _fingerprint(state) == before


def test_explicit_clear_changes_only_focus_and_is_idempotent():
    state = _state()
    object_id = _id()
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    before = _fingerprint(state)
    state.clear_focused_object()
    assert state.focus_state == FocusState()
    assert _fingerprint(state) == before
    cleared = state.focus_state
    state.clear_focused_object()
    assert state.focus_state is cleared


def test_successful_village_move_updates_location_and_clears_focus(capsys):
    state = _state()
    controller = ConsoleController(state, os.devnull)
    game_map = build_map(state.scenario)
    focused = _id("location/plaza")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    before = _fingerprint(state)
    controller._try_move(game_map, state.scenario, [], "north")
    capsys.readouterr()
    assert game_map.current == state.location == "well"
    assert state.focus_state == FocusState()
    assert state.turn == before["snapshot"]["turn"]
    assert state.rng.state() == before["rng"]
    assert state.log == before["log"]


def test_invalid_village_move_preserves_location_and_focus(capsys):
    state = _state()
    controller = ConsoleController(state, os.devnull)
    game_map = build_map(state.scenario)
    focused = _id("location/plaza")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    before = _fingerprint(state)
    controller._try_move(game_map, state.scenario, [], "upward-nowhere")
    capsys.readouterr()
    assert game_map.current == state.location == "plaza"
    assert state.focus_state.focused_object_id == focused
    assert _fingerprint(state) == before


def test_same_location_transition_preserves_focus_and_state():
    state = _state()
    focused = _id("location/plaza")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    focus_before = state.focus_state
    before = _fingerprint(state)
    state.transition_location(state.location)
    assert state.focus_state is focus_before
    assert _fingerprint(state) == before


def test_node_transition_clears_focus_without_other_side_effects():
    state = _state()
    focused = _id("object/road-sign")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    before = _fingerprint(state)
    state.transition_node("cave_entrance")
    assert state.node == "cave_entrance"
    assert state.focus_state == FocusState()
    after = _fingerprint(state)
    assert after["rng"] == before["rng"]
    assert after["log"] == before["log"]
    for key, value in before["snapshot"].items():
        if key != "node":
            assert after["snapshot"][key] == value


def test_same_node_transition_preserves_focus_and_state():
    state = _state()
    focused = _id("object/road-sign")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    focus_before = state.focus_state
    before = _fingerprint(state)
    state.transition_node(state.node)
    assert state.focus_state is focus_before
    assert _fingerprint(state) == before


def test_actual_goto_clears_focus_and_preserves_existing_log_contract():
    state = _state()
    focused = _id("object/road-sign")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    _goto(state, "cave_entrance")
    assert state.focus_state == FocusState()
    assert state.log == [{"t": 0, "type": "enter_node", "node": "cave_entrance"}]


def test_restore_clears_focus_without_changing_snapshot_schema():
    source = _state()
    source.hp = 11
    source.mp = 4
    source.turn = 9
    source.transition_node("cave_entrance")
    source.transition_location("well")
    snapshot = source.snapshot()
    assert not {"focus", "focus_state", "focused_object_id"} & snapshot.keys()

    restored = _state(seed=999)
    focused = _id("location/plaza")
    restored.set_focused_object(focused, focusable_object_ids=(focused,))
    restored.log.append({"t": 0, "type": "sentinel"})
    restored.restore(snapshot)
    assert restored.focus_state == FocusState()
    assert restored.snapshot() == snapshot
    assert restored.log == [{"t": 0, "type": "sentinel"}]


def test_load_failure_before_restore_preserves_focus_and_state(capsys):
    state = _state()
    focused = _id()
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    controller = ConsoleController(state, os.path.join("missing", "focus-audit"))
    before = _fingerprint(state)
    assert controller._load("does-not-exist") is False
    capsys.readouterr()
    assert state.focus_state.focused_object_id == focused
    assert _fingerprint(state) == before


def test_snapshot_schema_is_identical_before_and_after_focus():
    state = _state()
    before = state.snapshot()
    focused = _id()
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    assert state.snapshot() == before


def test_combat_entry_transition_clears_but_command_input_does_not(monkeypatch):
    state = _state()
    focused = _id("object/road-sign")
    state.set_focused_object(focused, focusable_object_ids=(focused,))
    combat_node = state.scenario.node("cave_entrance")
    _goto(state, combat_node.id)
    assert state.focus_state == FocusState()

    combat_focus = _id("object/combat-scene")
    state.set_focused_object(combat_focus, focusable_object_ids=(combat_focus,))
    controller = ConsoleController(state, os.devnull)
    enemies = state.scenario.make_group(combat_node.encounter)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "attack")
    assert controller.combat_command(state, enemies) == "attack"
    assert state.focus_state.focused_object_id == combat_focus
