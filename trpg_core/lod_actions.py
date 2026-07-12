"""Pure headless application boundary for canonical LOD actions."""

from __future__ import annotations

from dataclasses import dataclass

from .input_actions import (
    ApplyLodUnlockAction,
    InspectFocusedObjectAction,
    LodCanonicalAction,
    ObserveFocusedObjectAction,
)
from .lod import (
    ObjectAttentionState,
    ObjectLodState,
    attention_after_inspect,
    attention_after_observe,
    unlock_lod_cap,
)
from .lod_content import ObjectLodContentSpec, lod_content_for_world_object
from .world import WorldObjectId


@dataclass(frozen=True)
class ObjectLodProgress:
    object_id: WorldObjectId
    attention: ObjectAttentionState
    lod_state: ObjectLodState

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, WorldObjectId):
            raise ValueError("object_id must be a WorldObjectId")
        if not isinstance(self.attention, ObjectAttentionState):
            raise ValueError("attention must be an ObjectAttentionState")
        if not isinstance(self.lod_state, ObjectLodState):
            raise ValueError("lod_state must be an ObjectLodState")


@dataclass(frozen=True)
class LodRuntimeState:
    objects: tuple[ObjectLodProgress, ...] = ()

    def __post_init__(self) -> None:
        if type(self.objects) is not tuple:
            raise ValueError("objects must be a tuple")
        seen: set[WorldObjectId] = set()
        for progress in self.objects:
            if not isinstance(progress, ObjectLodProgress):
                raise ValueError("objects must contain only ObjectLodProgress values")
            if progress.object_id in seen:
                raise ValueError(f"duplicate LOD progress ID: {progress.object_id}")
            seen.add(progress.object_id)


def lod_progress_for_world_object(
    runtime: LodRuntimeState,
    object_id: WorldObjectId,
) -> ObjectLodProgress | None:
    if not isinstance(runtime, LodRuntimeState):
        raise ValueError("runtime must be a LodRuntimeState")
    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    return next((item for item in runtime.objects if item.object_id == object_id), None)


def initial_lod_progress(
    content: ObjectLodContentSpec,
    *,
    unlocked_lod_cap: int | None = None,
) -> ObjectLodProgress:
    if not isinstance(content, ObjectLodContentSpec):
        raise ValueError("content must be an ObjectLodContentSpec")
    cap = content.lod_spec.max_lod if unlocked_lod_cap is None else unlocked_lod_cap
    if type(cap) is not int or cap < 0 or cap > content.lod_spec.max_lod:
        raise ValueError("unlocked_lod_cap must be within the content LOD range")
    return ObjectLodProgress(
        content.lod_spec.object_id,
        ObjectAttentionState(0),
        ObjectLodState(cap),
    )


def add_lod_progress(
    runtime: LodRuntimeState,
    progress: ObjectLodProgress,
) -> LodRuntimeState:
    if not isinstance(runtime, LodRuntimeState):
        raise ValueError("runtime must be a LodRuntimeState")
    if not isinstance(progress, ObjectLodProgress):
        raise ValueError("progress must be an ObjectLodProgress")
    if lod_progress_for_world_object(runtime, progress.object_id) is not None:
        raise ValueError("LOD progress already exists for object")
    return LodRuntimeState(runtime.objects + (progress,))


def _validated_ids(
    values: tuple[WorldObjectId, ...],
    field_name: str,
) -> frozenset[WorldObjectId]:
    if type(values) is not tuple:
        raise ValueError(f"{field_name} must be a tuple")
    for value in values:
        if not isinstance(value, WorldObjectId):
            raise ValueError(f"{field_name} must contain only WorldObjectId values")
    result = frozenset(values)
    if len(result) != len(values):
        raise ValueError(f"{field_name} must not contain duplicates")
    return result


def _replace_progress(
    runtime: LodRuntimeState,
    replacement: ObjectLodProgress,
) -> LodRuntimeState:
    return LodRuntimeState(tuple(
        replacement if item.object_id == replacement.object_id else item
        for item in runtime.objects
    ))


def _focused_content(
    focused_object_id: WorldObjectId | None,
    focusable_ids: frozenset[WorldObjectId],
    scene_ids: frozenset[WorldObjectId],
) -> ObjectLodContentSpec:
    if focused_object_id is None:
        raise ValueError("focused_object_id is required")
    if not isinstance(focused_object_id, WorldObjectId):
        raise ValueError("focused_object_id must be a WorldObjectId or None")
    if focused_object_id not in focusable_ids:
        raise ValueError("focused object is not a current focus candidate")
    if focused_object_id not in scene_ids:
        raise ValueError("focused object is outside the current scene")
    content = lod_content_for_world_object(focused_object_id)
    if content is None:
        raise ValueError("focused object has no LOD content")
    return content


def apply_lod_action(
    runtime: LodRuntimeState,
    action: LodCanonicalAction,
    *,
    focused_object_id: WorldObjectId | None,
    focusable_object_ids: tuple[WorldObjectId, ...],
    scene_object_ids: tuple[WorldObjectId, ...],
) -> LodRuntimeState:
    """Validate authoritative context, then apply one immutable LOD update."""

    if not isinstance(runtime, LodRuntimeState):
        raise ValueError("runtime must be a LodRuntimeState")
    focusable_ids = _validated_ids(focusable_object_ids, "focusable_object_ids")
    scene_ids = _validated_ids(scene_object_ids, "scene_object_ids")
    if not focusable_ids.issubset(scene_ids):
        raise ValueError("focusable_object_ids must be a subset of scene_object_ids")

    if isinstance(action, (ObserveFocusedObjectAction, InspectFocusedObjectAction)):
        content = _focused_content(focused_object_id, focusable_ids, scene_ids)
        progress = lod_progress_for_world_object(runtime, content.lod_spec.object_id)
        if progress is None:
            progress = initial_lod_progress(content)
            runtime = add_lod_progress(runtime, progress)
        update = (attention_after_observe if isinstance(action, ObserveFocusedObjectAction)
                  else attention_after_inspect)
        replacement = ObjectLodProgress(
            progress.object_id, update(progress.attention), progress.lod_state,
        )
        return _replace_progress(runtime, replacement)

    if isinstance(action, ApplyLodUnlockAction):
        if action.object_id not in scene_ids:
            raise ValueError("unlock target is outside the current scene")
        content = lod_content_for_world_object(action.object_id)
        if content is None:
            raise ValueError("unlock target has no LOD content")
        progress = lod_progress_for_world_object(runtime, action.object_id)
        if progress is None:
            raise ValueError("unlock target has no LOD progress")
        replacement = ObjectLodProgress(
            progress.object_id,
            progress.attention,
            unlock_lod_cap(content.lod_spec, progress.lod_state, action.target_cap),
        )
        return _replace_progress(runtime, replacement)

    raise ValueError("unknown LOD action type")
