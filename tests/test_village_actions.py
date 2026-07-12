from __future__ import annotations

import copy
import builtins

import pytest

from trpg_core.input_actions import (
    ApplyLodUnlockAction, ClearFocusAction, DepartAction, ExploreAction,
    InspectFocusedObjectAction, MoveToLocationAction, ObserveFocusedObjectAction,
    SetFocusAction,
)
from trpg_core.map import build_map
from trpg_core.record import RecordingController
from trpg_core.replay import FixtureController
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import (
    GameState, _apply_village_action, _run_village, _village_context,
)
from trpg_core.session import ConsoleController
from trpg_core.world import location_world_object_id
from trpg_core.spatial import PlayerPosition


def _setup():
    scenario = load_scenario("goblin")
    state = GameState(7, scenario=scenario)
    game_map = build_map(scenario, state.location)
    return state, game_map


def _fingerprint(state, game_map):
    return (
        copy.deepcopy(state.snapshot()), state.rng.state(), copy.deepcopy(state.log),
        game_map.current, state.focus_state, state.lod_runtime, state.player_position,
    )


def test_game_state_owns_independent_exact_lod_runtime_values():
    first, _ = _setup()
    second, _ = _setup()
    assert first.lod_runtime is not second.lod_runtime
    with pytest.raises(ValueError, match="LodRuntimeState"):
        first.lod_runtime = {}


def test_shared_move_and_focus_guards_apply_canonical_events():
    state, game_map = _setup()
    picked = []
    plaza = location_world_object_id("goblin", "plaza")
    well = location_world_object_id("goblin", "well")
    before = _fingerprint(state, game_map)
    assert not _apply_village_action(state, game_map, picked, SetFocusAction(plaza))
    assert state.focus_state.focused_object_id == plaza
    assert state.rng.state() == before[1] and state.log == before[2]
    assert not _apply_village_action(state, game_map, picked, MoveToLocationAction(well))
    assert state.location == game_map.current == "well"
    assert state.player_position == PlayerPosition(1, 2)
    assert state.focus_state.focused_object_id is None
    assert not _apply_village_action(state, game_map, picked, ExploreAction("well"))
    assert picked == ["well"]


def test_coarse_scene_transition_sets_spawn_then_clears_position():
    state, game_map = _setup()
    picked = []
    well = location_world_object_id("goblin", "well")
    plaza = location_world_object_id("goblin", "plaza")
    assert not _apply_village_action(state, game_map, picked, MoveToLocationAction(well))
    assert state.player_position == PlayerPosition(1, 2)
    assert not _apply_village_action(state, game_map, picked, MoveToLocationAction(plaza))
    assert state.location == game_map.current == "plaza"
    assert state.player_position is None


def test_shared_dispatcher_applies_lod_actions_to_engine_owned_runtime():
    state, game_map = _setup()
    well = location_world_object_id("goblin", "well")
    game_map.current = "well"
    state.transition_location("well")
    assert not _apply_village_action(state, game_map, [], SetFocusAction(well))
    assert not _apply_village_action(state, game_map, [], ObserveFocusedObjectAction())
    progress = state.lod_runtime.objects[0]
    assert progress.object_id == well and progress.attention.attention_level == 1
    assert not _apply_village_action(state, game_map, [], InspectFocusedObjectAction())
    assert state.lod_runtime.objects[0].attention.attention_level == 3
    assert not _apply_village_action(state, game_map, [], ApplyLodUnlockAction(well, 3))
    assert state.lod_runtime.objects[0].lod_state.unlocked_lod_cap == 3


@pytest.mark.parametrize("action", [
    MoveToLocationAction(location_world_object_id("other", "well")),
    MoveToLocationAction(location_world_object_id("goblin", "forest_gate")),
    SetFocusAction(location_world_object_id("goblin", "well")),
    ObserveFocusedObjectAction(),
    ApplyLodUnlockAction(location_world_object_id("goblin", "well"), 1),
])
def test_invalid_canonical_events_are_rejected_before_state_change(action):
    state, game_map = _setup()
    before = _fingerprint(state, game_map)
    with pytest.raises(ValueError):
        _apply_village_action(state, game_map, [], action)
    assert _fingerprint(state, game_map) == before


def test_recording_controller_serializes_canonical_event_order():
    well = location_world_object_id("goblin", "well")
    events = iter((MoveToLocationAction(well), SetFocusAction(well),
                   ObserveFocusedObjectAction(), InspectFocusedObjectAction(),
                   ApplyLodUnlockAction(well, 3), ClearFocusAction(),
                   ExploreAction("well"), DepartAction()))
    class Base:
        def village_action(self, context, **display):
            return next(events)
    recorder = RecordingController(Base(), load_scenario("goblin"))
    returned = []
    for _ in range(8):
        event = recorder.village_action(None)
        returned.append(event)
        recorder.village_event_applied(event)
    assert returned == [MoveToLocationAction(well), SetFocusAction(well),
                        ObserveFocusedObjectAction(), InspectFocusedObjectAction(),
                        ApplyLodUnlockAction(well, 3), ClearFocusAction(),
                        ExploreAction("well"), DepartAction()]
    assert recorder.inputs == [
        "move-to:goblin:location/well", "focus:set:goblin:location/well",
        "observe", "inspect", "lod-unlock:goblin:location/well:3",
        "focus:clear", "explore:well", "depart",
    ]


def test_recording_controller_does_not_commit_rejected_village_event():
    state, game_map = _setup()
    class Base:
        def village_action(self, context, **display):
            return ObserveFocusedObjectAction()
    recorder = RecordingController(Base(), state.scenario)
    event = recorder.village_action(_village_context(state, game_map, []))
    with pytest.raises(ValueError, match="focused_object_id"):
        _apply_village_action(state, game_map, [], event)
    assert recorder.inputs == []


def test_fixture_controller_v1_restores_one_event_at_a_time_without_state_changes():
    scenario = load_scenario("goblin")
    tokens = ["move-to:goblin:location/well", "focus:set:goblin:location/well",
              "focus:clear", "explore:well", "depart"]
    controller = FixtureController(tokens, scenario, format_version=1)
    state, game_map = _setup()
    context = _village_context(state, game_map, [])
    before = _fingerprint(state, game_map)
    events = [controller.village_action(context) for _ in tokens]
    assert [type(event) for event in events] == [
        MoveToLocationAction, SetFocusAction, ClearFocusAction, ExploreAction, DepartAction,
    ]
    assert _fingerprint(state, game_map) == before
    controller.assert_all_events_consumed()


def test_fixture_controller_v2_restores_lod_events_without_state_changes():
    scenario = load_scenario("goblin")
    tokens = ["observe", "inspect", "lod-unlock:goblin:location/well:3"]
    controller = FixtureController(tokens, scenario, format_version=2)
    state, game_map = _setup()
    context = _village_context(state, game_map, [])
    before = _fingerprint(state, game_map)
    events = [controller.village_action(context) for _ in tokens]
    assert events == [
        ObserveFocusedObjectAction(), InspectFocusedObjectAction(),
        ApplyLodUnlockAction(location_world_object_id("goblin", "well"), 3),
    ]
    assert _fingerprint(state, game_map) == before
    controller.assert_all_events_consumed()


@pytest.mark.parametrize("raw, expected_type", [
    ("north", MoveToLocationAction),
    ("focus next", SetFocusAction),
    ("focus clear", ClearFocusAction),
    ("observe", ObserveFocusedObjectAction),
    ("inspect", InspectFocusedObjectAction),
])
def test_console_returns_one_canonical_event_without_applying_it(monkeypatch, raw, expected_type):
    state, game_map = _setup()
    controller = ConsoleController(state, "unused")
    context = _village_context(state, game_map, [])
    before = _fingerprint(state, game_map)
    monkeypatch.setattr(builtins, "input", lambda _prompt: raw)
    event = controller.village_action(context, game_map=game_map, picked=())
    assert isinstance(event, expected_type)
    assert _fingerprint(state, game_map) == before


def test_post_apply_observer_reads_authoritative_focus_and_skips_rejected_event():
    state, _game_map = _setup()
    plaza = location_world_object_id("goblin", "plaza")
    class Controller:
        def __init__(self, events):
            self.events = iter(events)
        def village_action(self, context, **display):
            return next(self.events)
    observed = []
    controller = Controller((SetFocusAction(plaza), ClearFocusAction(),
                             SetFocusAction(location_world_object_id("goblin", "well"))))
    with pytest.raises(ValueError):
        _run_village(
            state, controller,
            on_village_event_applied=lambda event, focused: observed.append((event, focused)),
        )
    assert observed == [(SetFocusAction(plaza), plaza), (ClearFocusAction(), None)]
