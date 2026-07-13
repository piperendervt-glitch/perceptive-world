from __future__ import annotations

import copy

import pytest

from trpg_core.input_actions import (
    ClearFocusAction,
    ExploreAction,
    InspectFocusedObjectAction,
    ObserveFocusedObjectAction,
    SetFocusAction,
)
from trpg_core.lod import ObjectAttentionState, ObjectLodState
from trpg_core.lod_actions import LodRuntimeState, ObjectLodProgress
from trpg_core.map import build_map
from trpg_core.presentation import (
    MemoryTagView,
    RememberedFactView,
    build_render_snapshot,
    focused_object_memory_views,
)
from trpg_core.record_codec import CURRENT_RECORD_FORMAT_VERSION
from trpg_core.replay import FixtureController
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import (
    CURRENT_SAVE_FORMAT_VERSION,
    GameState,
    _apply_village_action,
    _validated_save_state,
    make_save_document,
)
from trpg_core.trace_memory import MemoryState, ObjectTraceMap
from trpg_core.tui import screen_model_from_snapshot
from trpg_core.world import WorldObjectId, location_world_object_id


WELL = WorldObjectId("goblin", "location/well")


def _setup(location="well"):
    scenario = load_scenario("goblin")
    state = GameState(7, scenario=scenario)
    if location != state.location:
        if location == "lookout":
            state.transition_location("well")
        state.transition_location(location)
    game_map = build_map(scenario, state.location)
    return state, game_map


def _focus_well(state, game_map):
    _apply_village_action(state, game_map, (), SetFocusAction(WELL))


def _fingerprint(state):
    return (
        copy.deepcopy(state.snapshot()),
        state.rng.state(),
        copy.deepcopy(state.log),
        state.focus_state,
        state.lod_runtime,
        state.completed_village_actions,
        state.object_traces,
        state.memory_state,
    )


def _set_well_lod(state, lod):
    attention = (0, 1, 3, 6)[lod]
    state.lod_runtime = LodRuntimeState((ObjectLodProgress(
        WELL, ObjectAttentionState(attention), ObjectLodState(3),
    ),))


def test_game_state_owns_independent_exact_immutable_runtime_values():
    first, _ = _setup()
    second, _ = _setup()
    assert first.object_traces == ObjectTraceMap()
    assert first.memory_state == MemoryState()
    assert first.object_traces is not second.object_traces
    assert first.memory_state is not second.memory_state
    with pytest.raises(ValueError, match="ObjectTraceMap"):
        first.object_traces = {}
    with pytest.raises(ValueError, match="MemoryState"):
        first.memory_state = set()


def test_focus_alone_is_empty_and_clear_focus_preserves_trace_memory():
    state, game_map = _setup()
    _focus_well(state, game_map)
    assert state.object_traces == ObjectTraceMap()
    assert state.memory_state == MemoryState()
    _apply_village_action(state, game_map, (), ObserveFocusedObjectAction())
    acquired = state.object_traces, state.memory_state
    _apply_village_action(state, game_map, (), ClearFocusAction())
    assert (state.object_traces, state.memory_state) == acquired


def test_observe_captures_action_after_visible_facts_cumulatively_without_rng_or_turn():
    state, game_map = _setup()
    _focus_well(state, game_map)
    before = state.turn, state.rng.state()
    expected = (
        {"shape", "material", "age"},
        {"shape", "material", "age", "pulley", "rope"},
        {"shape", "material", "age", "pulley", "rope", "mark"},
    )
    for actions, keys in ((1, expected[0]), (2, expected[1]), (3, expected[2])):
        while len(state.lod_runtime.objects) == 0 or (
            state.lod_runtime.objects[0].attention.attention_level < (1, 3, 6)[actions - 1]
        ):
            _apply_village_action(state, game_map, (), ObserveFocusedObjectAction())
        trace = state.object_traces.get(WELL)
        assert {key.value for key in trace.remembered_fact_keys} == keys
    assert state.turn == before[0] and state.rng.state() == before[1]
    assert {tag.local_id for tag in state.memory_state.tags} == {"memory/well-faded-emblem"}
    again = state.object_traces, state.memory_state
    _apply_village_action(state, game_map, (), ObserveFocusedObjectAction())
    assert (state.object_traces, state.memory_state) == again


def test_inspect_and_observe_reach_the_same_action_after_trace():
    observed, observed_map = _setup()
    inspected, inspected_map = _setup()
    _focus_well(observed, observed_map)
    _focus_well(inspected, inspected_map)
    for _ in range(3):
        _apply_village_action(observed, observed_map, (), InspectFocusedObjectAction())
    for _ in range(6):
        _apply_village_action(inspected, inspected_map, (), ObserveFocusedObjectAction())
    assert observed.lod_runtime == inspected.lod_runtime
    assert observed.object_traces == inspected.object_traces
    assert observed.memory_state == inspected.memory_state
    assert observed.turn == inspected.turn == 0
    assert observed.rng.state() == inspected.rng.state()


@pytest.mark.parametrize("lod", [0, 1, 2, 3])
def test_explore_captures_current_lod_and_preserves_exactly_one_d6(lod):
    state, game_map = _setup()
    _set_well_lod(state, lod)
    expected_rng = copy.copy(state.rng)
    expected_rng.next()
    _apply_village_action(state, game_map, (), ExploreAction("well"))
    trace = state.object_traces.get(WELL)
    expected_keys = ({"shape"}, {"shape", "material", "age"},
                     {"shape", "material", "age", "pulley", "rope"},
                     {"shape", "material", "age", "pulley", "rope", "mark"})[lod]
    assert {key.value for key in trace.remembered_fact_keys} == expected_keys
    assert state.rng.state() == expected_rng.state()
    assert state.completed_village_actions == frozenset({"well"})
    assert bool(state.memory_state.tags) is (lod == 3)


def test_later_observe_adds_tag_without_upgrading_completed_well_effect():
    state, game_map = _setup()
    _set_well_lod(state, 2)
    _apply_village_action(state, game_map, (), ExploreAction("well"))
    effects = copy.deepcopy(state.effects)
    _focus_well(state, game_map)
    while not state.memory_state.tags:
        _apply_village_action(state, game_map, (), ObserveFocusedObjectAction())
    assert state.effects == effects
    assert len(state.memory_state.tags) == 1


@pytest.mark.parametrize("location,action", [
    ("shrine", ObserveFocusedObjectAction()),
    ("lookout", InspectFocusedObjectAction()),
    ("herbhut", ExploreAction("herbs")),
    ("elderhouse", ExploreAction("elder")),
])
def test_other_village_objects_remain_outside_f3(location, action):
    state, game_map = _setup(location)
    if isinstance(action, (ObserveFocusedObjectAction, InspectFocusedObjectAction)):
        object_id = location_world_object_id("goblin", location)
        _apply_village_action(state, game_map, (), SetFocusAction(object_id))
    _apply_village_action(state, game_map, (), action)
    assert state.object_traces == ObjectTraceMap()
    assert state.memory_state == MemoryState()


def test_invalid_action_and_candidate_failure_are_atomic(monkeypatch):
    state, game_map = _setup()
    before = _fingerprint(state)
    with pytest.raises(ValueError):
        _apply_village_action(state, game_map, (), ObserveFocusedObjectAction())
    assert _fingerprint(state) == before

    def fail_capture(_candidate):
        raise ValueError("candidate validation failed")

    monkeypatch.setattr("trpg_core.session._capture_well_trace_memory", fail_capture)
    with pytest.raises(ValueError, match="candidate validation"):
        _apply_village_action(state, game_map, (), ExploreAction("well"))
    assert _fingerprint(state) == before


def test_presentation_uses_safe_typed_labels_and_suppresses_current_duplicates():
    state, game_map = _setup()
    _set_well_lod(state, 3)
    _apply_village_action(state, game_map, (), ExploreAction("well"))
    _focus_well(state, game_map)
    remembered, tags = focused_object_memory_views(
        focused_object_id=WELL,
        object_traces=state.object_traces,
        memory_state=state.memory_state,
    )
    assert all(type(item) is RememberedFactView for item in remembered)
    assert tuple(item.label for item in remembered) == (
        "井戸らしき形", "石造り", "古い", "新しい滑車", "擦り切れた縄", "消えかけた紋章",
    )
    assert tags == (MemoryTagView("消えかけた紋章の記憶"),)
    snapshot = build_render_snapshot(
        state, active_game_map=game_map, lod_runtime=state.lod_runtime,
    )
    assert snapshot.focused_object_remembered_facts == ()
    assert snapshot.active_memory_tags == tags
    assert "goblin:" not in repr(tags) and "faded_emblem" not in repr(tags)
    assert "確定した記憶: 消えかけた紋章の記憶" in screen_model_from_snapshot(snapshot).lod_detail


def test_non_well_presentation_is_empty():
    state, game_map = _setup("lookout")
    lookout = location_world_object_id("goblin", "lookout")
    _apply_village_action(state, game_map, (), SetFocusAction(lookout))
    snapshot = build_render_snapshot(
        state, active_game_map=game_map, lod_runtime=state.lod_runtime,
    )
    assert snapshot.focused_object_remembered_facts == ()
    assert snapshot.active_memory_tags == ()


def test_save_v6_intentionally_omits_and_resets_runtime_trace_memory():
    state, game_map = _setup()
    _set_well_lod(state, 3)
    _apply_village_action(state, game_map, (), ExploreAction("well"))
    document = make_save_document(state)
    assert CURRENT_SAVE_FORMAT_VERSION == 6
    assert "object_traces" not in document and "memory_state" not in document
    loaded, _focused = _validated_save_state(document, state.scenario)
    assert loaded.object_traces == ObjectTraceMap()
    assert loaded.memory_state == MemoryState()
    assert loaded.lod_runtime == state.lod_runtime
    assert loaded.completed_village_actions == state.completed_village_actions
    assert loaded.effects == state.effects


def test_record_v7_replay_profile_keeps_legacy_empty_runtime():
    assert CURRENT_RECORD_FORMAT_VERSION == 7
    live, live_map = _setup()
    legacy, legacy_map = _setup()
    _set_well_lod(live, 3)
    _set_well_lod(legacy, 3)
    controller = FixtureController([], legacy.scenario, format_version=7)
    assert controller.trace_memory_profile == "legacy"
    _apply_village_action(live, live_map, (), ExploreAction("well"))
    _apply_village_action(
        legacy, legacy_map, (), ExploreAction("well"), trace_memory_profile="legacy",
    )
    assert live.object_traces != ObjectTraceMap() and live.memory_state != MemoryState()
    assert legacy.object_traces == ObjectTraceMap()
    assert legacy.memory_state == MemoryState()
