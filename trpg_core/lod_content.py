"""Immutable per-object LOD content with no runtime integration."""

from __future__ import annotations

from dataclasses import dataclass

from .lod import ObjectLodSpec
from .world import (
    VisibleWorldObjectFacts,
    WorldFact,
    WorldObjectFactPartition,
    WorldObjectId,
    partition_world_object_facts,
)


@dataclass(frozen=True)
class ObjectLodContentSpec:
    """Authoritative facts and cumulative visibility for one LOD spec."""

    lod_spec: ObjectLodSpec
    facts: tuple[WorldFact, ...]
    visible_fact_keys_by_lod: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.lod_spec, ObjectLodSpec):
            raise ValueError("lod_spec must be an ObjectLodSpec")
        if type(self.facts) is not tuple:
            raise ValueError("facts must be a tuple")
        fact_keys: set[str] = set()
        for fact in self.facts:
            if not isinstance(fact, WorldFact):
                raise ValueError("facts must contain only WorldFact values")
            if fact.key in fact_keys:
                raise ValueError(f"duplicate fact key: {fact.key}")
            fact_keys.add(fact.key)

        levels = self.visible_fact_keys_by_lod
        if type(levels) is not tuple:
            raise ValueError("visible_fact_keys_by_lod must be a tuple")
        if len(levels) != self.lod_spec.max_lod + 1:
            raise ValueError("visible level count must equal max_lod + 1")
        previous: frozenset[str] = frozenset()
        for level in levels:
            if type(level) is not tuple:
                raise ValueError("each visible fact key level must be a tuple")
            seen: set[str] = set()
            for key in level:
                if not isinstance(key, str) or not key:
                    raise ValueError("visible fact key must be a non-empty string")
                if key != key.strip():
                    raise ValueError("visible fact key must not have surrounding whitespace")
                if key in seen:
                    raise ValueError(f"duplicate visible fact key: {key}")
                if key not in fact_keys:
                    raise ValueError(f"unknown visible fact key: {key}")
                seen.add(key)
            current = frozenset(seen)
            if not previous.issubset(current):
                raise ValueError("visible fact keys must be cumulative")
            previous = current


def _validate_lod(content: ObjectLodContentSpec, lod: int) -> None:
    if not isinstance(content, ObjectLodContentSpec):
        raise ValueError("content must be an ObjectLodContentSpec")
    if type(lod) is not int or lod < 0 or lod > content.lod_spec.max_lod:
        raise ValueError("lod must be an int within the content LOD range")


def fact_partition_for_lod(
    content: ObjectLodContentSpec,
    lod: int,
) -> WorldObjectFactPartition:
    """Partition authoritative facts using the exact keys for ``lod``."""

    _validate_lod(content, lod)
    return partition_world_object_facts(
        content.facts,
        visible_fact_keys=content.visible_fact_keys_by_lod[lod],
    )


def visible_facts_for_lod(
    content: ObjectLodContentSpec,
    lod: int,
) -> VisibleWorldObjectFacts:
    """Return only facts safe to expose at ``lod``."""

    return VisibleWorldObjectFacts(fact_partition_for_lod(content, lod).visible)


GOBLIN_WELL_LOD_CONTENT = ObjectLodContentSpec(
    lod_spec=ObjectLodSpec(
        object_id=WorldObjectId("goblin", "location/well"),
        attention_thresholds=(0, 1, 3, 6),
    ),
    facts=(
        WorldFact("shape", "well_like"),
        WorldFact("material", "stone"),
        WorldFact("age", "old"),
        WorldFact("pulley", "recent"),
        WorldFact("rope", "worn"),
        WorldFact("mark", "faded_emblem"),
    ),
    visible_fact_keys_by_lod=(
        ("shape",),
        ("shape", "material", "age"),
        ("shape", "material", "age", "pulley", "rope"),
        ("shape", "material", "age", "pulley", "rope", "mark"),
    ),
)


def _village_content(scene: str, facts: tuple[WorldFact, ...]) -> ObjectLodContentSpec:
    keys = tuple(fact.key for fact in facts)
    return ObjectLodContentSpec(
        ObjectLodSpec(
            WorldObjectId("goblin", f"location/{scene}"),
            attention_thresholds=(0, 1, 3, 6),
        ),
        facts,
        ((keys[0],), keys[:2], keys[:3], keys),
    )


GOBLIN_SHRINE_LOD_CONTENT = _village_content("shrine", (
    WorldFact("shape", "small_shrine"),
    WorldFact("material", "weathered_stone"),
    WorldFact("offering", "kept_clean"),
    WorldFact("condition", "quietly_usable"),
))
GOBLIN_LOOKOUT_LOD_CONTENT = _village_content("lookout", (
    WorldFact("shape", "lookout_tower"),
    WorldFact("material", "timber"),
    WorldFact("view", "forest_edge_visible"),
    WorldFact("condition", "stable_vantage"),
))
GOBLIN_HERBHUT_LOD_CONTENT = _village_content("herbhut", (
    WorldFact("shape", "small_hut"),
    WorldFact("scent", "dried_herbs"),
    WorldFact("stock", "prepared_bundles"),
    WorldFact("condition", "carefully_sorted"),
))
GOBLIN_ELDERHOUSE_LOD_CONTENT = _village_content("elderhouse", (
    WorldFact("shape", "large_house"),
    WorldFact("material", "old_timber"),
    WorldFact("records", "village_notes"),
    WorldFact("condition", "orderly_meeting_place"),
))


_LOD_CONTENT = (
    GOBLIN_WELL_LOD_CONTENT,
    GOBLIN_SHRINE_LOD_CONTENT,
    GOBLIN_LOOKOUT_LOD_CONTENT,
    GOBLIN_HERBHUT_LOD_CONTENT,
    GOBLIN_ELDERHOUSE_LOD_CONTENT,
)


def lod_content_for_world_object(
    object_id: WorldObjectId,
) -> ObjectLodContentSpec | None:
    """Return content for an exact object ID, without fallback matching."""

    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    return next(
        (content for content in _LOD_CONTENT
         if content.lod_spec.object_id == object_id),
        None,
    )
