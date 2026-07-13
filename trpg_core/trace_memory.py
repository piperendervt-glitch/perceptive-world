"""Pure, immutable trace and memory values derived from scenario knowledge."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import IntEnum
import re

from .knowledge import KNOWN_COMPLETED_ACTIONS, ScenarioKnowledgeCatalog
from .world import WorldObjectId, serialize_world_object_id


_FACT_KEY_PATTERN = re.compile(r"[a-z][a-z0-9_]*\Z")
_SCENARIO_ID_PATTERN = re.compile(r"[a-z][a-z0-9_-]*\Z")
_MEMORY_LOCAL_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class TraceMemoryError(ValueError):
    """A trace or memory value violates the pure-domain contract."""


def _exact_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TraceMemoryError(f"{field_name} must be exact non-empty text")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise TraceMemoryError(f"{field_name} must not contain control characters")
    return value


@dataclass(frozen=True, order=True)
class WorldFactKey:
    """An object-scoped fact key; it is not globally unique by itself."""

    value: str

    def __post_init__(self) -> None:
        value = _exact_text(self.value, "fact key")
        if _FACT_KEY_PATTERN.fullmatch(value) is None:
            raise TraceMemoryError("fact key must use canonical lowercase key syntax")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, order=True)
class MemoryTagId:
    scenario_id: str
    local_id: str

    def __post_init__(self) -> None:
        scenario_id = _exact_text(self.scenario_id, "memory tag scenario_id")
        local_id = _exact_text(self.local_id, "memory tag local_id")
        if _SCENARIO_ID_PATTERN.fullmatch(scenario_id) is None:
            raise TraceMemoryError("memory tag scenario_id is not canonical")
        if not local_id.startswith("memory/"):
            raise TraceMemoryError("memory tag local_id must start with 'memory/'")
        suffix = local_id.removeprefix("memory/")
        if _MEMORY_LOCAL_ID_PATTERN.fullmatch(suffix) is None:
            raise TraceMemoryError("memory tag local ID is not canonical")


def parse_memory_tag_id(value: object) -> MemoryTagId:
    text = _exact_text(value, "memory tag ID")
    if text.count(":") != 1:
        raise TraceMemoryError("memory tag ID must contain one scenario separator")
    scenario_id, local_id = text.split(":", 1)
    return MemoryTagId(scenario_id, local_id)


def serialize_memory_tag_id(tag_id: MemoryTagId) -> str:
    if not isinstance(tag_id, MemoryTagId):
        raise TraceMemoryError("exact MemoryTagId is required")
    return f"{tag_id.scenario_id}:{tag_id.local_id}"


@dataclass(frozen=True)
class ObjectTraceState:
    remembered_fact_keys: frozenset[WorldFactKey] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.remembered_fact_keys) is not frozenset:
            raise TraceMemoryError("remembered_fact_keys must be a frozenset")
        if any(not isinstance(key, WorldFactKey) for key in self.remembered_fact_keys):
            raise TraceMemoryError("remembered_fact_keys must contain WorldFactKey values")


@dataclass(frozen=True)
class MemoryState:
    tags: frozenset[MemoryTagId] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if type(self.tags) is not frozenset:
            raise TraceMemoryError("tags must be a frozenset")
        if any(not isinstance(tag, MemoryTagId) for tag in self.tags):
            raise TraceMemoryError("tags must contain MemoryTagId values")


class TraceLevel(IntEnum):
    NONE = 0
    GLIMPSED = 1
    FAMILIAR = 2
    CLEAR = 3
    CONFIRMED = 4


def _catalog_object(object_id: WorldObjectId, catalog: ScenarioKnowledgeCatalog):
    if not isinstance(object_id, WorldObjectId):
        raise TraceMemoryError("exact WorldObjectId is required")
    if not isinstance(catalog, ScenarioKnowledgeCatalog):
        raise TraceMemoryError("exact ScenarioKnowledgeCatalog is required")
    if object_id.scenario_id != catalog.scenario_id:
        raise TraceMemoryError("object scenario does not match knowledge catalog")
    spec = catalog.object(object_id)
    if spec is None:
        raise TraceMemoryError("unknown knowledge object")
    return spec


def _fact_key_values(fact_keys: Iterable[WorldFactKey]) -> frozenset[WorldFactKey]:
    if isinstance(fact_keys, (str, bytes)) or not isinstance(fact_keys, Iterable):
        raise TraceMemoryError("fact_keys must be an iterable of WorldFactKey values")
    try:
        result = frozenset(fact_keys)
    except TypeError as exc:
        raise TraceMemoryError("fact_keys must contain hashable WorldFactKey values") from exc
    if any(not isinstance(key, WorldFactKey) for key in result):
        raise TraceMemoryError("fact_keys must contain WorldFactKey values")
    return result


def object_trace_state(
    *,
    object_id: WorldObjectId,
    fact_keys: Iterable[WorldFactKey],
    catalog: ScenarioKnowledgeCatalog,
) -> ObjectTraceState:
    spec = _catalog_object(object_id, catalog)
    keys = _fact_key_values(fact_keys)
    known = frozenset(fact.key for fact in spec.facts)
    unknown = sorted(key.value for key in keys if key.value not in known)
    if unknown:
        raise TraceMemoryError(f"unknown fact for object: {unknown[0]}")
    return ObjectTraceState(keys)


def remember_facts(
    *,
    object_id: WorldObjectId,
    trace: ObjectTraceState,
    fact_keys: Iterable[WorldFactKey],
    catalog: ScenarioKnowledgeCatalog,
) -> ObjectTraceState:
    if not isinstance(trace, ObjectTraceState):
        raise TraceMemoryError("trace must be an ObjectTraceState")
    current = object_trace_state(
        object_id=object_id,
        fact_keys=trace.remembered_fact_keys,
        catalog=catalog,
    )
    added = object_trace_state(
        object_id=object_id,
        fact_keys=fact_keys,
        catalog=catalog,
    )
    combined = current.remembered_fact_keys | added.remembered_fact_keys
    return trace if combined == current.remembered_fact_keys else ObjectTraceState(combined)


def remember_visible_facts(
    *,
    object_id: WorldObjectId,
    current_lod: int,
    trace: ObjectTraceState,
    catalog: ScenarioKnowledgeCatalog,
) -> ObjectTraceState:
    if type(current_lod) is not int or not 0 <= current_lod <= 3:
        raise TraceMemoryError("current_lod must be an exact int from 0 through 3")
    spec = _catalog_object(object_id, catalog)
    return remember_facts(
        object_id=object_id,
        trace=trace,
        fact_keys=(WorldFactKey(fact.key) for fact in spec.facts if fact.lod <= current_lod),
        catalog=catalog,
    )


def derive_trace_level(
    object_id: WorldObjectId,
    trace: ObjectTraceState,
    catalog: ScenarioKnowledgeCatalog,
) -> TraceLevel:
    if not isinstance(trace, ObjectTraceState):
        raise TraceMemoryError("trace must be an ObjectTraceState")
    spec = _catalog_object(object_id, catalog)
    validated = object_trace_state(
        object_id=object_id,
        fact_keys=trace.remembered_fact_keys,
        catalog=catalog,
    )
    remembered = frozenset(key.value for key in validated.remembered_fact_keys)
    level = TraceLevel.NONE
    for lod in range(4):
        required = frozenset(fact.key for fact in spec.facts if fact.lod <= lod)
        if not required.issubset(remembered):
            break
        level = TraceLevel(lod + 1)
    return level


def _catalog_memory_tag(tag_id: MemoryTagId, catalog: ScenarioKnowledgeCatalog):
    if not isinstance(tag_id, MemoryTagId):
        raise TraceMemoryError("exact MemoryTagId is required")
    if not isinstance(catalog, ScenarioKnowledgeCatalog):
        raise TraceMemoryError("exact ScenarioKnowledgeCatalog is required")
    if tag_id.scenario_id != catalog.scenario_id:
        raise TraceMemoryError("memory tag scenario does not match knowledge catalog")
    serialized = serialize_memory_tag_id(tag_id)
    spec = next((item for item in catalog.memory_tags if str(item.tag_id) == serialized), None)
    if spec is None:
        raise TraceMemoryError("unknown memory tag")
    return spec


def memory_state(
    tags: Iterable[MemoryTagId],
    *,
    catalog: ScenarioKnowledgeCatalog,
) -> MemoryState:
    if isinstance(tags, (str, bytes)) or not isinstance(tags, Iterable):
        raise TraceMemoryError("tags must be an iterable of MemoryTagId values")
    try:
        normalized = frozenset(tags)
    except TypeError as exc:
        raise TraceMemoryError("tags must contain hashable MemoryTagId values") from exc
    if any(not isinstance(tag, MemoryTagId) for tag in normalized):
        raise TraceMemoryError("tags must contain MemoryTagId values")
    for tag in normalized:
        _catalog_memory_tag(tag, catalog)
    return MemoryState(normalized)


def _completed_action_set(completed_actions: Iterable[str]) -> frozenset[str]:
    if isinstance(completed_actions, (str, bytes)) or not isinstance(
        completed_actions, Iterable,
    ):
        raise TraceMemoryError("completed_actions must be an iterable of exact action keys")
    try:
        result = frozenset(completed_actions)
    except TypeError as exc:
        raise TraceMemoryError("completed actions must be hashable strings") from exc
    for action in result:
        if not isinstance(action, str) or not action or action != action.strip():
            raise TraceMemoryError("completed action must be exact non-empty text")
        if action not in KNOWN_COMPLETED_ACTIONS:
            raise TraceMemoryError(f"unknown completed action: {action}")
    return result


def _validated_trace_mapping(
    object_traces: Mapping[WorldObjectId, ObjectTraceState],
    catalog: ScenarioKnowledgeCatalog,
) -> dict[WorldObjectId, ObjectTraceState]:
    if not isinstance(object_traces, Mapping):
        raise TraceMemoryError("object_traces must be a mapping")
    result = {}
    for object_id, trace in object_traces.items():
        if not isinstance(trace, ObjectTraceState):
            raise TraceMemoryError("object trace mapping values must be ObjectTraceState")
        result[object_id] = object_trace_state(
            object_id=object_id,
            fact_keys=trace.remembered_fact_keys,
            catalog=catalog,
        )
    return result


def derive_memory_tags(
    *,
    object_traces: Mapping[WorldObjectId, ObjectTraceState],
    completed_actions: Iterable[str],
    catalog: ScenarioKnowledgeCatalog,
) -> frozenset[MemoryTagId]:
    if not isinstance(catalog, ScenarioKnowledgeCatalog):
        raise TraceMemoryError("exact ScenarioKnowledgeCatalog is required")
    traces = _validated_trace_mapping(object_traces, catalog)
    actions = _completed_action_set(completed_actions)
    derived = set()
    for spec in catalog.memory_tags:
        facts_satisfied = all(
            reference.object_id in traces
            and WorldFactKey(reference.fact_key) in traces[
                reference.object_id
            ].remembered_fact_keys
            for reference in spec.required_facts
        )
        if facts_satisfied and frozenset(spec.required_completed_actions).issubset(actions):
            derived.add(parse_memory_tag_id(str(spec.tag_id)))
    return frozenset(derived)


def remember_derived_memory(
    current: MemoryState,
    derived: Iterable[MemoryTagId],
    catalog: ScenarioKnowledgeCatalog,
) -> MemoryState:
    if not isinstance(current, MemoryState):
        raise TraceMemoryError("current must be a MemoryState")
    validated_current = memory_state(current.tags, catalog=catalog)
    validated_derived = memory_state(derived, catalog=catalog)
    combined = validated_current.tags | validated_derived.tags
    return current if combined == validated_current.tags else MemoryState(combined)


@dataclass(frozen=True)
class ObjectTraceMap:
    entries: tuple[tuple[WorldObjectId, ObjectTraceState], ...] = ()

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple:
            raise TraceMemoryError("ObjectTraceMap entries must be a tuple")
        previous = None
        seen = set()
        for entry in self.entries:
            if type(entry) is not tuple or len(entry) != 2:
                raise TraceMemoryError("ObjectTraceMap entry must be an object/trace tuple")
            object_id, trace = entry
            if not isinstance(object_id, WorldObjectId) or not isinstance(trace, ObjectTraceState):
                raise TraceMemoryError("ObjectTraceMap entry has invalid values")
            serialized = serialize_world_object_id(object_id)
            if serialized in seen:
                raise TraceMemoryError("duplicate object trace entry")
            if previous is not None and serialized <= previous:
                raise TraceMemoryError("ObjectTraceMap entries must use canonical ordering")
            seen.add(serialized)
            previous = serialized

    def get(self, object_id: WorldObjectId) -> ObjectTraceState | None:
        if not isinstance(object_id, WorldObjectId):
            raise TraceMemoryError("exact WorldObjectId is required")
        return next((trace for key, trace in self.entries if key == object_id), None)


def object_trace_map(
    entries: Mapping[WorldObjectId, ObjectTraceState],
    *,
    catalog: ScenarioKnowledgeCatalog,
) -> ObjectTraceMap:
    validated = _validated_trace_mapping(entries, catalog)
    return ObjectTraceMap(tuple(sorted(
        validated.items(),
        key=lambda item: serialize_world_object_id(item[0]),
    )))


def update_object_trace_map(
    current: ObjectTraceMap,
    *,
    object_id: WorldObjectId,
    trace: ObjectTraceState,
    catalog: ScenarioKnowledgeCatalog,
) -> ObjectTraceMap:
    if not isinstance(current, ObjectTraceMap):
        raise TraceMemoryError("current must be an ObjectTraceMap")
    if not isinstance(trace, ObjectTraceState):
        raise TraceMemoryError("trace must be an ObjectTraceState")
    validated = object_trace_map(dict(current.entries), catalog=catalog)
    replacement = object_trace_state(
        object_id=object_id,
        fact_keys=trace.remembered_fact_keys,
        catalog=catalog,
    )
    values = dict(validated.entries)
    values[object_id] = replacement
    return object_trace_map(values, catalog=catalog)


def serialize_object_trace_state(trace: ObjectTraceState) -> dict[str, list[str]]:
    if not isinstance(trace, ObjectTraceState):
        raise TraceMemoryError("trace must be an ObjectTraceState")
    return {"remembered_fact_keys": sorted(key.value for key in trace.remembered_fact_keys)}


def deserialize_object_trace_state(
    value: object,
    *,
    object_id: WorldObjectId,
    catalog: ScenarioKnowledgeCatalog,
) -> ObjectTraceState:
    if type(value) is not dict or set(value) != {"remembered_fact_keys"}:
        raise TraceMemoryError("object trace data must contain only remembered_fact_keys")
    raw_keys = value["remembered_fact_keys"]
    if type(raw_keys) is not list:
        raise TraceMemoryError("remembered_fact_keys data must be a list")
    try:
        unique_keys = set(raw_keys)
    except TypeError as exc:
        raise TraceMemoryError("serialized fact keys must be hashable strings") from exc
    if len(raw_keys) != len(unique_keys):
        raise TraceMemoryError("duplicate serialized fact key")
    return object_trace_state(
        object_id=object_id,
        fact_keys=(WorldFactKey(key) for key in raw_keys),
        catalog=catalog,
    )


def serialize_memory_state(state: MemoryState) -> dict[str, list[str]]:
    if not isinstance(state, MemoryState):
        raise TraceMemoryError("state must be a MemoryState")
    return {"tags": sorted(serialize_memory_tag_id(tag) for tag in state.tags)}


def deserialize_memory_state(
    value: object,
    *,
    catalog: ScenarioKnowledgeCatalog,
) -> MemoryState:
    if type(value) is not dict or set(value) != {"tags"}:
        raise TraceMemoryError("memory data must contain only tags")
    raw_tags = value["tags"]
    if type(raw_tags) is not list:
        raise TraceMemoryError("serialized tags must be a list")
    try:
        unique_tags = set(raw_tags)
    except TypeError as exc:
        raise TraceMemoryError("serialized tags must be hashable strings") from exc
    if len(raw_tags) != len(unique_tags):
        raise TraceMemoryError("duplicate serialized memory tag")
    return memory_state(
        (parse_memory_tag_id(tag) for tag in raw_tags),
        catalog=catalog,
    )
