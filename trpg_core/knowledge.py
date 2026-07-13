"""Strict, immutable scenario knowledge catalogs loaded from YAML on demand."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Collection

import yaml

from .world import WorldObjectId, parse_world_object_id, serialize_world_object_id


KNOWLEDGE_SCHEMA_VERSION = 1
KNOWN_COMPLETED_ACTIONS = frozenset({"shrine", "scout", "herbs", "elder"})

# These are schema vocabulary, not object/fact associations. Associations live only
# in scenario knowledge YAML; Japanese display strings live in presentation.py.
KNOWN_FACT_LABEL_KEYS = frozenset({
    "well.shape.well_like", "well.material.stone", "well.age.old",
    "well.pulley.recent", "well.rope.worn", "well.mark.faded_emblem",
    "shrine.shape.small_shrine", "shrine.material.weathered_stone",
    "shrine.offering.kept_clean", "shrine.condition.quietly_usable",
    "lookout.shape.lookout_tower", "lookout.material.timber",
    "lookout.view.forest_edge_visible", "lookout.condition.stable_vantage",
    "herbhut.shape.small_hut", "herbhut.scent.dried_herbs",
    "herbhut.stock.prepared_bundles", "herbhut.condition.carefully_sorted",
    "elderhouse.shape.large_house", "elderhouse.material.old_timber",
    "elderhouse.records.village_notes", "elderhouse.condition.orderly_meeting_place",
})
KNOWN_MEMORY_LABEL_KEYS = frozenset({
    "memory.well.faded_emblem", "memory.shrine.blessing_site",
    "memory.lookout.surveyed", "memory.herbhut.supplies", "memory.elder.intel",
})


class KnowledgeCatalogError(ValueError):
    """The knowledge document is malformed or violates its closed schema."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise KnowledgeCatalogError(f"duplicate YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise KnowledgeCatalogError(f"{field} must be a non-empty untrimmed string")
    return value


def _mapping(value: object, field: str) -> dict:
    if type(value) is not dict:
        raise KnowledgeCatalogError(f"{field} must be a mapping")
    return value


def _sequence(value: object, field: str) -> list:
    if type(value) is not list:
        raise KnowledgeCatalogError(f"{field} must be a list")
    return value


def _fields(value: dict, required: Collection[str], field: str) -> None:
    expected = frozenset(required)
    actual = frozenset(value)
    missing = expected - actual
    unknown = actual - expected
    if missing:
        raise KnowledgeCatalogError(f"missing {field} field: {sorted(missing)[0]}")
    if unknown:
        raise KnowledgeCatalogError(f"unknown {field} field: {sorted(unknown)[0]}")


@dataclass(frozen=True, order=True)
class KnowledgeMemoryTagId:
    scenario_id: str
    local_id: str

    def __post_init__(self) -> None:
        _text(self.scenario_id, "memory tag scenario_id")
        local_id = _text(self.local_id, "memory tag local_id")
        if ":" in self.scenario_id or not local_id.startswith("memory/"):
            raise KnowledgeCatalogError("malformed memory tag ID")
        if local_id.endswith("/") or "//" in local_id:
            raise KnowledgeCatalogError("malformed memory tag ID")

    def __str__(self) -> str:
        return f"{self.scenario_id}:{self.local_id}"


def parse_knowledge_memory_tag_id(value: object) -> KnowledgeMemoryTagId:
    text = _text(value, "memory tag ID")
    if text.count(":") != 1:
        raise KnowledgeCatalogError("malformed memory tag ID")
    scenario_id, local_id = text.split(":", 1)
    return KnowledgeMemoryTagId(scenario_id, local_id)


@dataclass(frozen=True, order=True)
class KnowledgeFactSpec:
    key: str
    value: str
    lod: int
    label_key: str


@dataclass(frozen=True)
class KnowledgeObjectSpec:
    object_id: WorldObjectId
    facts: tuple[KnowledgeFactSpec, ...]

    def fact(self, key: str) -> KnowledgeFactSpec | None:
        _text(key, "fact key")
        return next((fact for fact in self.facts if fact.key == key), None)


@dataclass(frozen=True)
class KnowledgeFactReference:
    object_id: WorldObjectId
    fact_key: str


@dataclass(frozen=True)
class KnowledgeMemoryTagSpec:
    tag_id: KnowledgeMemoryTagId
    required_facts: tuple[KnowledgeFactReference, ...]
    required_completed_actions: tuple[str, ...]
    label_key: str


@dataclass(frozen=True)
class ScenarioKnowledgeCatalog:
    schema_version: int
    scenario_id: str
    objects: tuple[KnowledgeObjectSpec, ...]
    memory_tags: tuple[KnowledgeMemoryTagSpec, ...]

    def object(self, object_id: WorldObjectId) -> KnowledgeObjectSpec | None:
        if not isinstance(object_id, WorldObjectId):
            raise ValueError("exact WorldObjectId is required")
        return next((item for item in self.objects if item.object_id == object_id), None)

    def fact(self, object_id: WorldObjectId, fact_key: str) -> KnowledgeFactSpec | None:
        item = self.object(object_id)
        return None if item is None else item.fact(fact_key)

    def memory_tag(self, tag_id: KnowledgeMemoryTagId) -> KnowledgeMemoryTagSpec | None:
        if not isinstance(tag_id, KnowledgeMemoryTagId):
            raise ValueError("exact KnowledgeMemoryTagId is required")
        return next((item for item in self.memory_tags if item.tag_id == tag_id), None)


def _parse_object_id(value: object, scenario_id: str) -> WorldObjectId:
    try:
        object_id = parse_world_object_id(_text(value, "object ID"))
    except ValueError as exc:
        raise KnowledgeCatalogError(f"malformed object ID: {value!r}") from exc
    if object_id.scenario_id != scenario_id:
        raise KnowledgeCatalogError("object namespace does not match scenario_id")
    return object_id


def _parse_fact(key: object, raw: object) -> KnowledgeFactSpec:
    fact_key = _text(key, "fact key")
    data = _mapping(raw, f"fact {fact_key}")
    _fields(data, {"value", "lod", "label_key"}, f"fact {fact_key}")
    value = _text(data["value"], f"fact {fact_key} value")
    lod = data["lod"]
    if type(lod) is not int or not 0 <= lod <= 3:
        raise KnowledgeCatalogError("fact lod must be an exact int from 0 through 3")
    label_key = _text(data["label_key"], f"fact {fact_key} label_key")
    if label_key not in KNOWN_FACT_LABEL_KEYS:
        raise KnowledgeCatalogError(f"unknown fact label key: {label_key}")
    return KnowledgeFactSpec(fact_key, value, lod, label_key)


def _parse_memory_tag(
    key: object,
    raw: object,
    scenario_id: str,
    objects: tuple[KnowledgeObjectSpec, ...],
) -> KnowledgeMemoryTagSpec:
    tag_id = parse_knowledge_memory_tag_id(key)
    if tag_id.scenario_id != scenario_id:
        raise KnowledgeCatalogError("memory tag namespace does not match scenario_id")
    data = _mapping(raw, f"memory tag {tag_id}")
    _fields(
        data,
        {"required_facts", "required_completed_actions", "label_key"},
        f"memory tag {tag_id}",
    )
    references = []
    seen_references = set()
    for index, raw_reference in enumerate(_sequence(
        data["required_facts"], f"memory tag {tag_id} required_facts",
    )):
        reference = _mapping(raw_reference, f"required fact {index}")
        _fields(reference, {"object_id", "fact_key"}, f"required fact {index}")
        object_id = _parse_object_id(reference["object_id"], scenario_id)
        fact_key = _text(reference["fact_key"], "required fact key")
        parsed = KnowledgeFactReference(object_id, fact_key)
        if parsed in seen_references:
            raise KnowledgeCatalogError("duplicate required fact")
        seen_references.add(parsed)
        target = next((item for item in objects if item.object_id == object_id), None)
        if target is None or target.fact(fact_key) is None:
            raise KnowledgeCatalogError("dangling required fact")
        references.append(parsed)

    actions = []
    seen_actions = set()
    for raw_action in _sequence(
        data["required_completed_actions"],
        f"memory tag {tag_id} required_completed_actions",
    ):
        action = _text(raw_action, "completed action prerequisite")
        if action not in KNOWN_COMPLETED_ACTIONS:
            raise KnowledgeCatalogError(f"unknown completed action prerequisite: {action}")
        if action in seen_actions:
            raise KnowledgeCatalogError("duplicate completed action prerequisite")
        seen_actions.add(action)
        actions.append(action)

    label_key = _text(data["label_key"], f"memory tag {tag_id} label_key")
    if label_key not in KNOWN_MEMORY_LABEL_KEYS:
        raise KnowledgeCatalogError(f"unknown memory label key: {label_key}")
    return KnowledgeMemoryTagSpec(
        tag_id,
        tuple(sorted(
            references,
            key=lambda item: (serialize_world_object_id(item.object_id), item.fact_key),
        )),
        tuple(sorted(actions)),
        label_key,
    )


def load_knowledge_catalog(
    path: str | Path,
    *,
    expected_scenario_id: str,
) -> ScenarioKnowledgeCatalog:
    """Load and atomically validate a complete knowledge document."""

    expected = _text(expected_scenario_id, "expected_scenario_id")
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as stream:
            raw = yaml.load(stream, Loader=_UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise KnowledgeCatalogError(f"cannot load knowledge catalog: {source}") from exc
    data = _mapping(raw, "knowledge document")
    _fields(data, {"schema_version", "scenario_id", "objects", "memory_tags"}, "top-level")
    version = data["schema_version"]
    if type(version) is not int or version != KNOWLEDGE_SCHEMA_VERSION:
        raise KnowledgeCatalogError(f"unsupported knowledge schema version: {version!r}")
    scenario_id = _text(data["scenario_id"], "scenario_id")
    if scenario_id != expected:
        raise KnowledgeCatalogError("scenario_id does not match expected scenario")

    objects = []
    for raw_id, raw_object in _mapping(data["objects"], "objects").items():
        object_id = _parse_object_id(raw_id, scenario_id)
        object_data = _mapping(raw_object, f"object {raw_id}")
        _fields(object_data, {"facts"}, f"object {raw_id}")
        facts = tuple(
            _parse_fact(key, value)
            for key, value in _mapping(object_data["facts"], f"object {raw_id} facts").items()
        )
        if not facts:
            raise KnowledgeCatalogError("knowledge object must contain facts")
        objects.append(KnowledgeObjectSpec(object_id, facts))
    normalized_objects = tuple(sorted(objects, key=lambda item: serialize_world_object_id(item.object_id)))

    memory_tags = tuple(sorted(
        (
            _parse_memory_tag(key, value, scenario_id, normalized_objects)
            for key, value in _mapping(data["memory_tags"], "memory_tags").items()
        ),
        key=lambda item: str(item.tag_id),
    ))
    return ScenarioKnowledgeCatalog(version, scenario_id, normalized_objects, memory_tags)


def production_knowledge_path(scenario_id: str) -> Path:
    scenario = _text(scenario_id, "scenario_id")
    return Path(__file__).parent.parent / "scenarios" / f"{scenario}_knowledge.yaml"


@lru_cache(maxsize=1)
def _cached_goblin_knowledge_catalog() -> ScenarioKnowledgeCatalog:
    return load_knowledge_catalog(
        production_knowledge_path("goblin"),
        expected_scenario_id="goblin",
    )


def goblin_knowledge_catalog() -> ScenarioKnowledgeCatalog:
    """Load the sole production goblin catalog lazily and atomically."""

    return _cached_goblin_knowledge_catalog()
