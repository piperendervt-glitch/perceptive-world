"""Pure LOD effect registry for the goblin village preparation actions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .world import WorldObjectId


@dataclass(frozen=True)
class VillageEffectDelta:
    global_hit_bonus: int = 0
    watcher_hit_bonus: int = 0
    chief_hit_bonus: int = 0
    herbs_delta: int = 0
    grants_recon: bool = False

    def __post_init__(self) -> None:
        for name in (
            "global_hit_bonus", "watcher_hit_bonus",
            "chief_hit_bonus", "herbs_delta",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative int")
        if type(self.grants_recon) is not bool:
            raise ValueError("grants_recon must be a bool")


@dataclass(frozen=True)
class VillageLodEffectSpec:
    object_id: WorldObjectId
    action_key: str
    effects_by_lod: Mapping[int, VillageEffectDelta]
    legacy_effect: VillageEffectDelta

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, WorldObjectId):
            raise ValueError("object_id must be a WorldObjectId")
        if type(self.action_key) is not str or not self.action_key:
            raise ValueError("action_key must be non-empty text")
        if not isinstance(self.effects_by_lod, Mapping):
            raise ValueError("effects_by_lod must be a mapping")
        copied = dict(self.effects_by_lod)
        if set(copied) != {0, 1, 2, 3}:
            raise ValueError("effects_by_lod must define exactly LOD 0 through 3")
        for lod, effect in copied.items():
            if type(lod) is not int or not isinstance(effect, VillageEffectDelta):
                raise ValueError("invalid LOD effect entry")
        if not isinstance(self.legacy_effect, VillageEffectDelta):
            raise ValueError("legacy_effect must be a VillageEffectDelta")
        object.__setattr__(self, "effects_by_lod", MappingProxyType(copied))


def _spec(scene: str, action: str, levels, legacy) -> VillageLodEffectSpec:
    return VillageLodEffectSpec(
        WorldObjectId("goblin", f"location/{scene}"), action,
        {index: value for index, value in enumerate(levels)}, legacy,
    )


NONE = VillageEffectDelta()
SHRINE_EFFECT_SPEC = _spec("shrine", "shrine", (
    NONE,
    VillageEffectDelta(chief_hit_bonus=1),
    VillageEffectDelta(global_hit_bonus=1),
    VillageEffectDelta(global_hit_bonus=2),
), VillageEffectDelta(global_hit_bonus=1))
SCOUT_EFFECT_SPEC = _spec("lookout", "scout", (
    NONE,
    VillageEffectDelta(watcher_hit_bonus=1),
    VillageEffectDelta(grants_recon=True),
    VillageEffectDelta(chief_hit_bonus=1, grants_recon=True),
), VillageEffectDelta(grants_recon=True))
HERBS_EFFECT_SPEC = _spec("herbhut", "herbs", (
    NONE,
    VillageEffectDelta(herbs_delta=1),
    VillageEffectDelta(herbs_delta=2),
    VillageEffectDelta(herbs_delta=3),
), VillageEffectDelta(herbs_delta=2))
ELDER_EFFECT_SPEC = _spec("elderhouse", "elder", (
    NONE,
    VillageEffectDelta(chief_hit_bonus=1),
    VillageEffectDelta(chief_hit_bonus=2),
    VillageEffectDelta(chief_hit_bonus=3),
), VillageEffectDelta(chief_hit_bonus=2))

VILLAGE_LOD_EFFECT_SPECS = (
    SHRINE_EFFECT_SPEC, SCOUT_EFFECT_SPEC, HERBS_EFFECT_SPEC, ELDER_EFFECT_SPEC,
)


def village_lod_effect_spec(
    object_id: WorldObjectId, action_key: str,
) -> VillageLodEffectSpec:
    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    if type(action_key) is not str or not action_key:
        raise ValueError("action_key must be non-empty text")
    exact_object = next(
        (spec for spec in VILLAGE_LOD_EFFECT_SPECS if spec.object_id == object_id), None,
    )
    if exact_object is None:
        raise ValueError("unknown village LOD effect object")
    if exact_object.action_key != action_key:
        raise ValueError("village object and action key do not match")
    return exact_object


def village_effect_for_lod(
    object_id: WorldObjectId, action_key: str, lod: int, *, legacy: bool = False,
) -> VillageEffectDelta:
    if type(lod) is not int or not 0 <= lod <= 3:
        raise ValueError("village effect LOD must be an int from 0 through 3")
    if type(legacy) is not bool:
        raise ValueError("legacy must be a bool")
    spec = village_lod_effect_spec(object_id, action_key)
    return spec.legacy_effect if legacy else spec.effects_by_lod[lod]
