"""Pure per-object attention and LOD contracts.

This module deliberately has no runtime integration.  Attention changes and
cap unlocks remain the responsibility of later canonical actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from .world import WorldObjectId


def _require_non_negative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative int")
    return value


@dataclass(frozen=True)
class ObjectAttentionState:
    """Current attention for one object; LOD is derived, not stored."""

    attention_level: int

    def __post_init__(self) -> None:
        _require_non_negative_int(self.attention_level, "attention_level")


@dataclass(frozen=True)
class ObjectLodState:
    """Highest LOD currently unlocked for one object."""

    unlocked_lod_cap: int

    def __post_init__(self) -> None:
        _require_non_negative_int(self.unlocked_lod_cap, "unlocked_lod_cap")


@dataclass(frozen=True)
class ObjectLodSpec:
    """Stable object identity and minimum attention required for each LOD."""

    object_id: WorldObjectId
    attention_thresholds: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, WorldObjectId):
            raise ValueError("object_id must be a WorldObjectId")
        thresholds = self.attention_thresholds
        if type(thresholds) is not tuple:
            raise ValueError("attention_thresholds must be a tuple")
        if not thresholds:
            raise ValueError("attention_thresholds must not be empty")
        for threshold in thresholds:
            _require_non_negative_int(threshold, "attention threshold")
        if thresholds[0] != 0:
            raise ValueError("first attention threshold must be 0")
        if any(left >= right for left, right in zip(thresholds, thresholds[1:])):
            raise ValueError("attention thresholds must be strictly increasing")

    @property
    def max_lod(self) -> int:
        return len(self.attention_thresholds) - 1


def lod_from_attention(
    spec: ObjectLodSpec,
    attention: ObjectAttentionState,
) -> int:
    """Return the highest LOD whose threshold is met by attention."""

    if not isinstance(spec, ObjectLodSpec):
        raise ValueError("spec must be an ObjectLodSpec")
    if not isinstance(attention, ObjectAttentionState):
        raise ValueError("attention must be an ObjectAttentionState")
    return max(
        index
        for index, threshold in enumerate(spec.attention_thresholds)
        if attention.attention_level >= threshold
    )


def derive_current_lod(
    spec: ObjectLodSpec,
    attention: ObjectAttentionState,
    lod_state: ObjectLodState,
) -> int:
    """Derive current LOD from attention and the validated unlocked cap."""

    if not isinstance(lod_state, ObjectLodState):
        raise ValueError("lod_state must be an ObjectLodState")
    if not isinstance(spec, ObjectLodSpec):
        raise ValueError("spec must be an ObjectLodSpec")
    if lod_state.unlocked_lod_cap > spec.max_lod:
        raise ValueError("unlocked_lod_cap exceeds spec max_lod")
    return min(
        lod_from_attention(spec, attention),
        lod_state.unlocked_lod_cap,
        spec.max_lod,
    )


def attention_after_focus_change(
    state: ObjectAttentionState,
) -> ObjectAttentionState:
    """Initial policy: changing focus preserves attention without decay."""

    if not isinstance(state, ObjectAttentionState):
        raise ValueError("state must be an ObjectAttentionState")
    return state


def attention_after_scene_leave(
    state: ObjectAttentionState,
) -> ObjectAttentionState:
    """Initial policy: leaving a scene preserves attention without decay."""

    if not isinstance(state, ObjectAttentionState):
        raise ValueError("state must be an ObjectAttentionState")
    return state
