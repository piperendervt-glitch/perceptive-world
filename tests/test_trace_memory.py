from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect

import pytest

from trpg_core.knowledge import goblin_knowledge_catalog
from trpg_core.trace_memory import (
    MemoryState,
    MemoryTagId,
    ObjectTraceMap,
    ObjectTraceState,
    TraceLevel,
    TraceMemoryError,
    WorldFactKey,
    derive_memory_tags,
    derive_trace_level,
    deserialize_memory_state,
    deserialize_object_trace_state,
    memory_state,
    object_trace_map,
    object_trace_state,
    parse_memory_tag_id,
    remember_derived_memory,
    remember_facts,
    remember_visible_facts,
    serialize_memory_state,
    serialize_memory_tag_id,
    serialize_object_trace_state,
    update_object_trace_map,
)
from trpg_core.world import WorldObjectId, serialize_world_object_id


CATALOG = goblin_knowledge_catalog()
OBJECTS = tuple(item.object_id for item in CATALOG.objects)
WELL = WorldObjectId("goblin", "location/well")


def _key(value):
    return WorldFactKey(value)


def _trace(object_id, *keys):
    return object_trace_state(
        object_id=object_id,
        fact_keys=map(_key, keys),
        catalog=CATALOG,
    )


def _tag(value):
    return parse_memory_tag_id(value)


def test_world_fact_key_is_exact_immutable_hashable_and_orderable():
    shape = WorldFactKey("shape")
    assert str(shape) == "shape"
    assert {shape} == {WorldFactKey("shape")}
    assert sorted((shape, WorldFactKey("rope"))) == [WorldFactKey("rope"), shape]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        shape.value = "changed"


@pytest.mark.parametrize("value", [
    "", " ", " shape", "shape ", "Shape", "消えかけた紋章",
    "shape-label", "shape\n", "shape\x00", True, 1, None,
])
def test_world_fact_key_rejects_malformed_and_presentation_values(value):
    with pytest.raises(TraceMemoryError):
        WorldFactKey(value)


def test_memory_tag_id_round_trip_is_exact_immutable_hashable_and_orderable():
    text = "goblin:memory/well-faded-emblem"
    tag = parse_memory_tag_id(text)
    assert tag == MemoryTagId("goblin", "memory/well-faded-emblem")
    assert serialize_memory_tag_id(tag) == text
    assert parse_memory_tag_id(serialize_memory_tag_id(tag)) == tag
    assert hash(tag) == hash(MemoryTagId("goblin", "memory/well-faded-emblem"))
    assert sorted((MemoryTagId("goblin", "memory/z"), tag))[0] == tag
    with pytest.raises((FrozenInstanceError, AttributeError)):
        tag.local_id = "memory/changed"


@pytest.mark.parametrize("value", [
    "", "goblin", "memory/well", ":memory/well", "goblin:",
    "goblin:well", "goblin:memory/", "Goblin:memory/well",
    "goblin:memory/Well", "goblin:memory/well label",
    "goblin:memory/well:extra", " goblin:memory/well", True, 1, None,
])
def test_memory_tag_id_rejects_partial_malformed_and_label_values(value):
    with pytest.raises(TraceMemoryError):
        parse_memory_tag_id(value)


def test_empty_trace_is_first_class_strict_and_immutable():
    state = ObjectTraceState()
    assert state.remembered_fact_keys == frozenset()
    assert _trace(WELL) == state
    with pytest.raises((FrozenInstanceError, AttributeError)):
        state.remembered_fact_keys = frozenset({_key("shape")})
    with pytest.raises(TraceMemoryError):
        ObjectTraceState([_key("shape")])
    with pytest.raises(TraceMemoryError):
        ObjectTraceState(frozenset({"shape"}))


def test_trace_factory_collapses_duplicates_and_validates_object_scope():
    state = object_trace_state(
        object_id=WELL,
        fact_keys=[_key("shape"), _key("shape")],
        catalog=CATALOG,
    )
    assert state.remembered_fact_keys == frozenset({_key("shape")})
    with pytest.raises(TraceMemoryError, match="unknown fact"):
        _trace(WELL, "missing")
    with pytest.raises(TraceMemoryError, match="unknown fact"):
        _trace(WorldObjectId("goblin", "location/shrine"), "mark")
    with pytest.raises(TraceMemoryError, match="unknown knowledge object"):
        _trace(WorldObjectId("goblin", "location/missing"), "shape")
    with pytest.raises(TraceMemoryError, match="scenario"):
        _trace(WorldObjectId("other", "location/well"), "shape")


def test_trace_union_is_monotonic_idempotent_commutative_and_associative():
    empty = _trace(WELL)
    a, b, c = _key("shape"), _key("material"), _key("age")

    def add(state, keys):
        return remember_facts(
            object_id=WELL, trace=state, fact_keys=keys, catalog=CATALOG,
        )

    ab = add(add(empty, [a]), [b])
    ba = add(add(empty, [b]), [a])
    assert ab == ba
    assert add(ab, [a]) is ab
    assert add(ab, []) is ab
    assert ab.remembered_fact_keys.issuperset(empty.remembered_fact_keys)
    left = add(add(empty, [a, b]), [c])
    right = add(add(empty, [a]), [b, c])
    assert left == right
    assert add(empty, [c, a, b]) == add(empty, [b, c, a]) == left


@pytest.mark.parametrize("bad", ["shape", ["shape"], [1], [["shape"]], None])
def test_trace_union_rejects_malformed_or_unknown_additions(bad):
    with pytest.raises(TraceMemoryError):
        remember_facts(
            object_id=WELL, trace=_trace(WELL), fact_keys=bad, catalog=CATALOG,
        )
    with pytest.raises(TraceMemoryError, match="unknown fact"):
        remember_facts(
            object_id=WELL,
            trace=_trace(WELL),
            fact_keys=[_key("missing")],
            catalog=CATALOG,
        )


@pytest.mark.parametrize("object_id", OBJECTS, ids=serialize_world_object_id)
@pytest.mark.parametrize("lod", range(4))
def test_visible_capture_uses_exact_cumulative_catalog_facts(object_id, lod):
    spec = CATALOG.object(object_id)
    result = remember_visible_facts(
        object_id=object_id,
        current_lod=lod,
        trace=_trace(object_id),
        catalog=CATALOG,
    )
    expected = frozenset(_key(fact.key) for fact in spec.facts if fact.lod <= lod)
    higher = frozenset(_key(fact.key) for fact in spec.facts if fact.lod > lod)
    assert result.remembered_fact_keys == expected
    assert result.remembered_fact_keys.isdisjoint(higher)
    assert remember_visible_facts(
        object_id=object_id,
        current_lod=lod,
        trace=_trace(object_id),
        catalog=CATALOG,
    ) == result


@pytest.mark.parametrize("lod", [True, False, -1, 4, 1.0, "1", None])
def test_visible_capture_rejects_invalid_lod(lod):
    with pytest.raises(TraceMemoryError, match="current_lod"):
        remember_visible_facts(
            object_id=WELL,
            current_lod=lod,
            trace=_trace(WELL),
            catalog=CATALOG,
        )


@pytest.mark.parametrize("object_id", OBJECTS, ids=serialize_world_object_id)
def test_trace_level_requires_contiguous_complete_lod_prefix(object_id):
    empty = _trace(object_id)
    assert derive_trace_level(object_id, empty, CATALOG) is TraceLevel.NONE
    for lod, expected in enumerate((
        TraceLevel.GLIMPSED,
        TraceLevel.FAMILIAR,
        TraceLevel.CLEAR,
        TraceLevel.CONFIRMED,
    )):
        trace = remember_visible_facts(
            object_id=object_id,
            current_lod=lod,
            trace=empty,
            catalog=CATALOG,
        )
        assert derive_trace_level(object_id, trace, CATALOG) is expected


def test_trace_level_does_not_promote_from_partial_high_tier_facts():
    assert derive_trace_level(WELL, _trace(WELL, "mark"), CATALOG) is TraceLevel.NONE
    partial = _trace(WELL, "shape", "pulley", "rope", "mark")
    assert derive_trace_level(WELL, partial, CATALOG) is TraceLevel.GLIMPSED
    missing_lod_one = _trace(WELL, "shape", "material", "pulley", "rope", "mark")
    assert derive_trace_level(WELL, missing_lod_one, CATALOG) is TraceLevel.GLIMPSED
    with pytest.raises(TraceMemoryError, match="unknown knowledge object"):
        derive_trace_level(
            WorldObjectId("goblin", "location/missing"), ObjectTraceState(), CATALOG,
        )


def _prerequisite_traces(tag_spec):
    grouped = {}
    for reference in tag_spec.required_facts:
        grouped.setdefault(reference.object_id, []).append(_key(reference.fact_key))
    return {
        object_id: object_trace_state(
            object_id=object_id, fact_keys=keys, catalog=CATALOG,
        )
        for object_id, keys in grouped.items()
    }


@pytest.mark.parametrize("tag_spec", CATALOG.memory_tags, ids=lambda item: str(item.tag_id))
def test_memory_derivation_uses_only_catalog_prerequisites(tag_spec):
    expected = _tag(str(tag_spec.tag_id))
    traces = _prerequisite_traces(tag_spec)
    actions = list(tag_spec.required_completed_actions)
    assert expected not in derive_memory_tags(
        object_traces={}, completed_actions=actions, catalog=CATALOG,
    )
    if actions:
        assert expected not in derive_memory_tags(
            object_traces=traces, completed_actions=[], catalog=CATALOG,
        )
    derived = derive_memory_tags(
        object_traces=traces, completed_actions=actions, catalog=CATALOG,
    )
    assert expected in derived
    assert derive_memory_tags(
        object_traces=dict(reversed(tuple(traces.items()))),
        completed_actions=list(reversed(actions)),
        catalog=CATALOG,
    ) == derived
    assert derive_memory_tags(
        object_traces=traces,
        completed_actions=actions + actions,
        catalog=CATALOG,
    ) == derived
    assert all(isinstance(tag, MemoryTagId) for tag in derived)


def test_memory_derivation_rejects_unknown_actions_and_malformed_traces():
    with pytest.raises(TraceMemoryError, match="unknown completed action"):
        derive_memory_tags(
            object_traces={}, completed_actions=["missing"], catalog=CATALOG,
        )
    with pytest.raises(TraceMemoryError, match="completed_actions"):
        derive_memory_tags(
            object_traces={}, completed_actions="shrine", catalog=CATALOG,
        )
    with pytest.raises(TraceMemoryError, match="hashable"):
        derive_memory_tags(
            object_traces={}, completed_actions=[["shrine"]], catalog=CATALOG,
        )
    with pytest.raises(TraceMemoryError, match="mapping"):
        derive_memory_tags(
            object_traces=[], completed_actions=[], catalog=CATALOG,
        )


def test_memory_derivation_never_adds_facts_or_gameplay_data():
    traces = {WELL: _trace(WELL, "mark")}
    before = dict(traces)
    derived = derive_memory_tags(
        object_traces=traces, completed_actions=[], catalog=CATALOG,
    )
    assert _tag("goblin:memory/well-faded-emblem") in derived
    assert traces == before
    state = memory_state(derived, catalog=CATALOG)
    assert tuple(field_name for field_name in state.__dict__) == ("tags",)


def test_memory_state_union_is_empty_monotonic_idempotent_and_strict():
    empty = memory_state([], catalog=CATALOG)
    assert empty == MemoryState()
    well = _tag("goblin:memory/well-faded-emblem")
    first = remember_derived_memory(empty, [well, well], CATALOG)
    assert first.tags == frozenset({well})
    assert remember_derived_memory(first, [well], CATALOG) is first
    with pytest.raises((FrozenInstanceError, AttributeError)):
        first.tags = frozenset()
    with pytest.raises(TraceMemoryError, match="unknown memory tag"):
        memory_state([MemoryTagId("goblin", "memory/missing")], catalog=CATALOG)
    with pytest.raises(TraceMemoryError, match="scenario"):
        memory_state([MemoryTagId("other", "memory/well")], catalog=CATALOG)
    with pytest.raises(TraceMemoryError):
        MemoryState([well])


def test_object_trace_map_is_canonical_exact_and_immutable_on_update():
    shrine = WorldObjectId("goblin", "location/shrine")
    mapping = object_trace_map(
        {WELL: _trace(WELL, "shape"), shrine: _trace(shrine, "shape")},
        catalog=CATALOG,
    )
    assert tuple(serialize_world_object_id(key) for key, _ in mapping.entries) == tuple(sorted(
        (serialize_world_object_id(WELL), serialize_world_object_id(shrine)),
    ))
    assert mapping.get(WELL) == _trace(WELL, "shape")
    assert mapping.get(WorldObjectId("goblin", "location/lookout")) is None
    updated = update_object_trace_map(
        mapping,
        object_id=WELL,
        trace=_trace(WELL, "shape", "material"),
        catalog=CATALOG,
    )
    assert mapping.get(WELL) == _trace(WELL, "shape")
    assert updated.get(WELL) == _trace(WELL, "shape", "material")
    with pytest.raises(TraceMemoryError, match="canonical ordering"):
        ObjectTraceMap(tuple(reversed(mapping.entries)))
    with pytest.raises(TraceMemoryError, match="unknown knowledge object"):
        object_trace_map(
            {WorldObjectId("goblin", "location/missing"): ObjectTraceState()},
            catalog=CATALOG,
        )


def test_trace_and_memory_serialization_are_canonical_strict_and_round_trip():
    trace = _trace(WELL, "rope", "shape", "material")
    trace_data = serialize_object_trace_state(trace)
    assert trace_data == {"remembered_fact_keys": ["material", "rope", "shape"]}
    assert deserialize_object_trace_state(
        trace_data, object_id=WELL, catalog=CATALOG,
    ) == trace
    well = _tag("goblin:memory/well-faded-emblem")
    shrine = _tag("goblin:memory/shrine-blessing-site")
    state = memory_state([shrine, well], catalog=CATALOG)
    memory_data = serialize_memory_state(state)
    assert memory_data == {"tags": sorted((
        "goblin:memory/shrine-blessing-site",
        "goblin:memory/well-faded-emblem",
    ))}
    assert deserialize_memory_state(memory_data, catalog=CATALOG) == state


@pytest.mark.parametrize("value", [
    {}, {"remembered_fact_keys": [], "unknown": True},
    {"remembered_fact_keys": "shape"},
    {"remembered_fact_keys": ["shape", "shape"]},
    {"remembered_fact_keys": [["shape"]]},
    {"remembered_fact_keys": ["missing"]},
])
def test_trace_deserialization_rejects_malformed_data(value):
    with pytest.raises(TraceMemoryError):
        deserialize_object_trace_state(value, object_id=WELL, catalog=CATALOG)


@pytest.mark.parametrize("value", [
    {}, {"tags": [], "unknown": True}, {"tags": "tag"},
    {"tags": ["goblin:memory/well-faded-emblem"] * 2},
    {"tags": [["goblin:memory/well-faded-emblem"]]},
    {"tags": ["goblin:memory/missing"]},
])
def test_memory_deserialization_rejects_malformed_data(value):
    with pytest.raises(TraceMemoryError):
        deserialize_memory_state(value, catalog=CATALOG)


def test_module_dependency_boundary_contains_no_runtime_integration():
    import trpg_core.trace_memory as module

    source = inspect.getsource(module)
    for forbidden in (
        ".session", ".presentation", ".record", ".replay", "tkinter",
        "GameState", "CURRENT_SAVE_FORMAT_VERSION", "CURRENT_RECORD_FORMAT_VERSION",
    ):
        assert forbidden not in source
    for forbidden_field in (
        "current_lod", "timestamp", "last_seen", "confidence", "effect", "label",
    ):
        assert forbidden_field not in ObjectTraceState.__dataclass_fields__
        assert forbidden_field not in MemoryState.__dataclass_fields__


def test_architecture_versions_and_existing_modules_remain_unconnected():
    import trpg_core.presentation as presentation_module
    import trpg_core.record_codec as record_codec_module
    import trpg_core.session as session_module

    assert session_module.CURRENT_SAVE_FORMAT_VERSION == 6
    assert record_codec_module.CURRENT_RECORD_FORMAT_VERSION == 7
    assert "trace_memory" not in inspect.getsource(session_module)
    assert "trace_memory" not in inspect.getsource(presentation_module)
    assert "trace_memory" not in inspect.getsource(record_codec_module)
