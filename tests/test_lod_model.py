import dataclasses

import pytest

from trpg_core.lod import (
    ObjectAttentionState,
    ObjectLodSpec,
    ObjectLodState,
    attention_after_focus_change,
    attention_after_scene_leave,
    derive_current_lod,
    lod_from_attention,
)
from trpg_core.world import WorldObjectId


def _object_id():
    return WorldObjectId("goblin", "location/well")


def _spec(thresholds=(0, 1, 3, 6)):
    return ObjectLodSpec(_object_id(), thresholds)


@pytest.mark.parametrize("value", [0, 1, 10**30])
def test_attention_accepts_non_negative_int_and_is_frozen(value):
    state = ObjectAttentionState(value)
    assert state.attention_level == value
    assert not hasattr(state, "current_lod")
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.attention_level = 0


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "1", None])
def test_attention_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="attention_level"):
        ObjectAttentionState(value)


@pytest.mark.parametrize("value", [0, 1, 99])
def test_lod_state_accepts_non_negative_int_and_is_frozen(value):
    state = ObjectLodState(value)
    assert state.unlocked_lod_cap == value
    assert not hasattr(state, "current_lod")
    assert not hasattr(state, "attention_level")
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.unlocked_lod_cap = 0


@pytest.mark.parametrize("value", [-1, True, False, 1.0, "1", None])
def test_lod_state_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="unlocked_lod_cap"):
        ObjectLodState(value)


def test_lod_spec_is_frozen_keeps_world_object_id_and_derives_max_lod():
    spec = _spec()
    assert spec.object_id == _object_id()
    assert spec.attention_thresholds == (0, 1, 3, 6)
    assert spec.max_lod == 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.attention_thresholds = (0,)


@pytest.mark.parametrize("thresholds", [
    (), [0, 1], (1, 2), (0, -1), (0, True), (0, 1.0),
    (0, 1, 1), (0, 3, 2), (0, 2, 1, 3),
])
def test_lod_spec_rejects_invalid_thresholds(thresholds):
    with pytest.raises(ValueError):
        ObjectLodSpec(_object_id(), thresholds)


def test_lod_spec_rejects_invalid_object_id():
    with pytest.raises(ValueError, match="WorldObjectId"):
        ObjectLodSpec("goblin:location/well", (0,))


@pytest.mark.parametrize("level, expected", [
    (0, 0), (1, 1), (2, 1), (3, 2), (5, 2), (6, 3), (100, 3),
])
def test_lod_from_attention_follows_thresholds(level, expected):
    spec = _spec()
    attention = ObjectAttentionState(level)
    before = (spec, attention)
    assert lod_from_attention(spec, attention) == expected
    assert lod_from_attention(spec, attention) == expected
    assert (spec, attention) == before


@pytest.mark.parametrize("attention, cap, expected", [
    (0, 3, 0), (5, 1, 1), (5, 2, 2), (5, 3, 2),
    (100, 3, 3), (100, 0, 0),
])
def test_current_lod_is_derived_from_attention_and_cap(attention, cap, expected):
    spec = _spec()
    attention_state = ObjectAttentionState(attention)
    lod_state = ObjectLodState(cap)
    before = (spec, attention_state, lod_state)
    assert derive_current_lod(spec, attention_state, lod_state) == expected
    assert (spec, attention_state, lod_state) == before
    assert not hasattr(lod_state, "current_lod")


def test_current_lod_rejects_cap_above_spec_max_without_clamping():
    with pytest.raises(ValueError, match="exceeds"):
        derive_current_lod(_spec(), ObjectAttentionState(100), ObjectLodState(4))


@pytest.mark.parametrize("transition", [
    attention_after_focus_change,
    attention_after_scene_leave,
])
@pytest.mark.parametrize("level", [0, 7])
def test_initial_transitions_preserve_attention_without_decay(transition, level):
    state = ObjectAttentionState(level)
    before = dataclasses.asdict(state)
    assert transition(state) == ObjectAttentionState(level)
    assert dataclasses.asdict(state) == before


def test_lod_module_has_no_runtime_dependency_cycle():
    import trpg_core.lod as lod
    import trpg_core.presentation
    import trpg_core.session
    import trpg_core.world as world

    assert lod.ObjectLodSpec.__module__ == "trpg_core.lod"
    assert not hasattr(world, "ObjectLodSpec")
