from dataclasses import FrozenInstanceError, fields

import pytest

from trpg_core.input_actions import (
    ApplyLodUnlockAction,
    InspectFocusedObjectAction,
    ObserveFocusedObjectAction,
)
from trpg_core.lod import ObjectAttentionState, ObjectLodState, derive_current_lod
from trpg_core.lod_actions import (
    LodRuntimeState,
    ObjectLodProgress,
    add_lod_progress,
    apply_lod_action,
    initial_lod_progress,
    lod_progress_for_world_object,
)
from trpg_core.lod_content import (
    GOBLIN_WELL_LOD_CONTENT,
    visible_facts_for_lod,
)
from trpg_core.world import WorldObjectId


WELL = WorldObjectId("goblin", "location/well")
CONTEXT = dict(
    focused_object_id=WELL,
    focusable_object_ids=(WELL,),
    scene_object_ids=(WELL,),
)


def _apply(runtime, action, **overrides):
    context = CONTEXT | overrides
    return apply_lod_action(runtime, action, **context)


def _well(runtime):
    return lod_progress_for_world_object(runtime, WELL)


def _lod(progress):
    return derive_current_lod(
        GOBLIN_WELL_LOD_CONTENT.lod_spec, progress.attention, progress.lod_state,
    )


def _visible(progress):
    return tuple(f.key for f in visible_facts_for_lod(
        GOBLIN_WELL_LOD_CONTENT, _lod(progress),
    ).facts)


def test_progress_and_runtime_are_frozen_minimal_and_strict():
    progress = initial_lod_progress(GOBLIN_WELL_LOD_CONTENT)
    assert [f.name for f in fields(progress)] == ["object_id", "attention", "lod_state"]
    assert [f.name for f in fields(LodRuntimeState())] == ["objects"]
    for value in (progress, LodRuntimeState((progress,))):
        with pytest.raises(FrozenInstanceError):
            value.extra = 1
    with pytest.raises(ValueError):
        ObjectLodProgress("bad", ObjectAttentionState(0), ObjectLodState(1))
    with pytest.raises(ValueError):
        ObjectLodProgress(WELL, "bad", ObjectLodState(1))
    with pytest.raises(ValueError):
        ObjectLodProgress(WELL, ObjectAttentionState(0), "bad")
    with pytest.raises(ValueError):
        LodRuntimeState([])
    with pytest.raises(ValueError):
        LodRuntimeState(("bad",))
    with pytest.raises(ValueError):
        LodRuntimeState((progress, progress))


def test_exact_query_and_pure_append_preserve_order():
    other = ObjectLodProgress(WorldObjectId("other", "location/well"),
                              ObjectAttentionState(9), ObjectLodState(0))
    runtime = LodRuntimeState((other,))
    progress = initial_lod_progress(GOBLIN_WELL_LOD_CONTENT)
    result = add_lod_progress(runtime, progress)
    assert result.objects == (other, progress)
    assert runtime.objects == (other,)
    assert lod_progress_for_world_object(result, WELL) == progress
    assert lod_progress_for_world_object(result, WorldObjectId("goblin", "other")) is None
    with pytest.raises(ValueError):
        add_lod_progress(result, progress)


@pytest.mark.parametrize("cap", [0, 1, 3])
def test_initial_progress_uses_zero_attention_and_explicit_valid_cap(cap):
    progress = initial_lod_progress(GOBLIN_WELL_LOD_CONTENT, unlocked_lod_cap=cap)
    assert progress == ObjectLodProgress(WELL, ObjectAttentionState(0), ObjectLodState(cap))


def test_initial_progress_defaults_to_content_max_lod():
    assert initial_lod_progress(GOBLIN_WELL_LOD_CONTENT).lod_state == ObjectLodState(3)


@pytest.mark.parametrize("cap", [-1, 4, True, False, 1.0, "1"])
def test_initial_progress_rejects_invalid_cap(cap):
    with pytest.raises(ValueError):
        initial_lod_progress(GOBLIN_WELL_LOD_CONTENT, unlocked_lod_cap=cap)


@pytest.mark.parametrize("field, value", [
    ("focusable_object_ids", [WELL]),
    ("scene_object_ids", [WELL]),
    ("focusable_object_ids", (WELL, WELL)),
    ("scene_object_ids", (WELL, WELL)),
    ("focusable_object_ids", (WELL,)),
])
def test_context_validation_rejects_mutable_duplicate_or_non_subset(field, value):
    overrides = {field: value}
    if field == "focusable_object_ids" and value == (WELL,):
        overrides["scene_object_ids"] = ()
    with pytest.raises(ValueError):
        _apply(LodRuntimeState(), ObserveFocusedObjectAction(), **overrides)


def test_observe_and_inspect_initialize_then_update_only_focused_entry():
    other = ObjectLodProgress(WorldObjectId("other", "object/x"),
                              ObjectAttentionState(7), ObjectLodState(0))
    runtime = LodRuntimeState((other,))
    observed = _apply(runtime, ObserveFocusedObjectAction())
    inspected = _apply(observed, InspectFocusedObjectAction())
    assert _well(observed).attention == ObjectAttentionState(1)
    assert _well(inspected).attention == ObjectAttentionState(3)
    assert _well(inspected).lod_state == ObjectLodState(3)
    assert inspected.objects[0] is other
    assert runtime.objects == (other,)


def test_vertical_action_sequence_derives_lods_and_visible_facts():
    runtime = LodRuntimeState()
    expected = [
        (1, 1, ("shape", "material", "age")),
        (3, 2, ("shape", "material", "age", "pulley", "rope")),
        (4, 2, ("shape", "material", "age", "pulley", "rope")),
        (6, 3, ("shape", "material", "age", "pulley", "rope", "mark")),
    ]
    for action, wanted in zip(
        (ObserveFocusedObjectAction(), InspectFocusedObjectAction(),
         ObserveFocusedObjectAction(), InspectFocusedObjectAction()), expected,
    ):
        previous = runtime
        runtime = _apply(runtime, action)
        progress = _well(runtime)
        assert (progress.attention.attention_level, _lod(progress), _visible(progress)) == wanted
        assert previous != runtime
    assert not hasattr(_well(runtime), "current_lod")


def test_unlock_requires_progress_is_monotonic_and_preserves_attention():
    progress = initial_lod_progress(GOBLIN_WELL_LOD_CONTENT, unlocked_lod_cap=1)
    runtime = LodRuntimeState((ObjectLodProgress(
        WELL, ObjectAttentionState(6), progress.lod_state,
    ),))
    assert _lod(_well(runtime)) == 1 and "mark" not in _visible(_well(runtime))
    unlocked = _apply(runtime, ApplyLodUnlockAction(WELL, 3))
    assert _well(unlocked).attention == ObjectAttentionState(6)
    assert _lod(_well(unlocked)) == 3 and "mark" in _visible(_well(unlocked))
    assert _apply(unlocked, ApplyLodUnlockAction(WELL, 3)) == unlocked
    with pytest.raises(ValueError):
        _apply(unlocked, ApplyLodUnlockAction(WELL, 2))
    with pytest.raises(ValueError):
        _apply(LodRuntimeState(), ApplyLodUnlockAction(WELL, 1))


@pytest.mark.parametrize("action, overrides", [
    (ObserveFocusedObjectAction(), {"focused_object_id": None}),
    (InspectFocusedObjectAction(), {"focused_object_id": None}),
    (ObserveFocusedObjectAction(), {"focusable_object_ids": ()}),
    (InspectFocusedObjectAction(), {"scene_object_ids": ()}),
    (ObserveFocusedObjectAction(), {
        "focused_object_id": WorldObjectId("other", "location/well"),
        "focusable_object_ids": (WorldObjectId("other", "location/well"),),
        "scene_object_ids": (WorldObjectId("other", "location/well"),),
    }),
    (ApplyLodUnlockAction(WELL, 1), {"scene_object_ids": ()}),
])
def test_invalid_or_stale_actions_leave_runtime_unchanged(action, overrides):
    runtime = LodRuntimeState()
    with pytest.raises(ValueError):
        _apply(runtime, action, **overrides)
    assert runtime == LodRuntimeState()


def test_unknown_action_is_rejected_without_runtime_change():
    runtime = LodRuntimeState()
    with pytest.raises(ValueError, match="unknown"):
        _apply(runtime, object())
    assert runtime == LodRuntimeState()
