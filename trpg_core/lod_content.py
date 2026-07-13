"""Immutable per-object LOD content with no runtime integration."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .knowledge import KnowledgeObjectSpec, goblin_knowledge_catalog
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


def _content_from_knowledge(spec: KnowledgeObjectSpec) -> ObjectLodContentSpec:
    """Adapt one immutable knowledge object without creating another authority."""

    facts = tuple(WorldFact(fact.key, fact.value) for fact in spec.facts)
    return ObjectLodContentSpec(
        ObjectLodSpec(
            spec.object_id,
            attention_thresholds=(0, 1, 3, 6),
        ),
        facts,
        tuple(
            tuple(fact.key for fact in spec.facts if fact.lod <= lod)
            for lod in range(4)
        ),
    )


@lru_cache(maxsize=1)
def _cached_goblin_lod_contents() -> tuple[ObjectLodContentSpec, ...]:
    return tuple(_content_from_knowledge(spec) for spec in goblin_knowledge_catalog().objects)


def goblin_lod_contents() -> tuple[ObjectLodContentSpec, ...]:
    """Build the complete production LOD catalog lazily from knowledge YAML."""

    return _cached_goblin_lod_contents()


def lod_content_for_world_object(
    object_id: WorldObjectId,
) -> ObjectLodContentSpec | None:
    """Return content for an exact object ID, without fallback matching."""

    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    if object_id.scenario_id != "goblin":
        return None
    return next(
        (content for content in goblin_lod_contents()
         if content.lod_spec.object_id == object_id),
        None,
    )
