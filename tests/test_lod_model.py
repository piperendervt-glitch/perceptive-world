import dataclasses

import pytest

from trpg_core.lod import (
    ObjectAttentionState,
    ObjectLodSpec,
    ObjectLodState,
    apply_attention_gain,
    attention_after_focus_change,
    attention_after_inspect,
    attention_after_observe,
    attention_after_scene_leave,
    derive_current_lod,
    lod_from_attention,
    unlock_lod_cap,
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


@pytest.mark.parametrize("level, gain, expected", [
    (0, 1, 1), (4, 2, 6), (10**30, 10**20, 10**30 + 10**20),
])
def test_apply_attention_gain_adds_without_clamping(level, gain, expected):
    state = ObjectAttentionState(level)
    before = state
    first = apply_attention_gain(state, gain)
    second = apply_attention_gain(state, gain)
    assert first == second == ObjectAttentionState(expected)
    assert state == before
    assert not hasattr(first, "current_lod")


@pytest.mark.parametrize("gain", [0, -1, True, False, 1.0, "1", None])
def test_apply_attention_gain_rejects_non_positive_or_non_int(gain):
    with pytest.raises(ValueError, match="positive int"):
        apply_attention_gain(ObjectAttentionState(0), gain)


@pytest.mark.parametrize("level, expected", [(0, 1), (1, 2), (100, 101)])
def test_observe_adds_exactly_one(level, expected):
    state = ObjectAttentionState(level)
    assert attention_after_observe(state) == ObjectAttentionState(expected)
    assert attention_after_observe(state) == ObjectAttentionState(expected)
    assert state == ObjectAttentionState(level)


@pytest.mark.parametrize("level, expected", [(0, 2), (1, 3), (100, 102)])
def test_inspect_adds_exactly_two(level, expected):
    state = ObjectAttentionState(level)
    assert attention_after_inspect(state) == ObjectAttentionState(expected)
    assert attention_after_inspect(state) == ObjectAttentionState(expected)
    assert state == ObjectAttentionState(level)


def test_observe_and_inspect_accumulate_across_lod_thresholds():
    spec = _spec()
    states = [ObjectAttentionState(0)]
    states.append(attention_after_observe(states[-1]))
    states.append(attention_after_inspect(states[-1]))
    states.append(attention_after_observe(states[-1]))
    states.append(attention_after_inspect(states[-1]))
    assert [state.attention_level for state in states] == [0, 1, 3, 4, 6]
    assert [lod_from_attention(spec, state) for state in states] == [0, 1, 2, 2, 3]


def test_attention_accumulates_beyond_cap_without_clamping():
    spec = _spec()
    attention = ObjectAttentionState(0)
    for _ in range(3):
        attention = attention_after_inspect(attention)
    assert attention.attention_level == 6
    assert lod_from_attention(spec, attention) == 3
    assert derive_current_lod(spec, attention, ObjectLodState(1)) == 1


@pytest.mark.parametrize("current, target, expected", [
    (0, 1, 1), (1, 2, 2), (1, 1, 1),
])
def test_unlock_lod_cap_is_monotonic_and_idempotent(current, target, expected):
    spec = _spec()
    state = ObjectLodState(current)
    before = (spec, state)
    assert unlock_lod_cap(spec, state, target) == ObjectLodState(expected)
    assert (spec, state) == before


@pytest.mark.parametrize("target", [-1, True, False, 1.0, "1", None])
def test_unlock_lod_cap_rejects_invalid_target(target):
    with pytest.raises(ValueError):
        unlock_lod_cap(_spec(), ObjectLodState(1), target)


def test_unlock_lod_cap_rejects_decrease_excess_and_corrupt_existing_cap():
    spec = _spec()
    with pytest.raises(ValueError, match="decrease"):
        unlock_lod_cap(spec, ObjectLodState(1), 0)
    with pytest.raises(ValueError, match="target_cap exceeds"):
        unlock_lod_cap(spec, ObjectLodState(1), 4)
    with pytest.raises(ValueError, match="existing.*exceeds"):
        unlock_lod_cap(spec, ObjectLodState(4), 3)


@pytest.mark.parametrize("attention, old_cap, target, old_lod, new_lod", [
    (6, 1, 3, 1, 3),
    (2, 1, 3, 1, 1),
    (100, 0, 2, 0, 2),
])
def test_current_lod_is_derived_after_unlock(
    attention, old_cap, target, old_lod, new_lod,
):
    spec = _spec()
    attention_state = ObjectAttentionState(attention)
    old_state = ObjectLodState(old_cap)
    assert derive_current_lod(spec, attention_state, old_state) == old_lod
    new_state = unlock_lod_cap(spec, old_state, target)
    assert derive_current_lod(spec, attention_state, new_state) == new_lod
    assert not hasattr(new_state, "current_lod")


def test_d1_preservation_rules_remain_distinct_from_explicit_updates():
    state = ObjectAttentionState(5)
    assert attention_after_focus_change(state) == state
    assert attention_after_scene_leave(state) == state
    assert attention_after_observe(state) == ObjectAttentionState(6)
    assert attention_after_inspect(state) == ObjectAttentionState(7)
