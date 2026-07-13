from dataclasses import FrozenInstanceError, fields

import pytest

from trpg_core.knowledge import goblin_knowledge_catalog
from trpg_core.lod import (
    ObjectAttentionState,
    ObjectLodSpec,
    ObjectLodState,
    attention_after_inspect,
    attention_after_observe,
    derive_current_lod,
)
from trpg_core.lod_content import (
    ObjectLodContentSpec,
    fact_partition_for_lod,
    lod_content_for_world_object,
    visible_facts_for_lod,
)
from trpg_core.world import (
    VisibleWorldObjectFacts,
    WorldFact,
    WorldObjectId,
    partition_world_object_facts,
    serialize_world_object_id,
)


GOBLIN_WELL_LOD_CONTENT = lod_content_for_world_object(
    WorldObjectId("goblin", "location/well"),
)


def _content(*, facts=None, levels=None, thresholds=(0, 2)):
    facts = facts if facts is not None else (
        WorldFact("a", "one"), WorldFact("b", "two"),
    )
    levels = levels if levels is not None else (("a",), ("a", "b"))
    return ObjectLodContentSpec(
        ObjectLodSpec(WorldObjectId("test", "object/x"), thresholds),
        facts,
        levels,
    )


def _keys(facts):
    return tuple(fact.key for fact in facts)


def test_content_model_is_frozen_and_keeps_only_companion_fields():
    content = _content()
    assert [field.name for field in fields(content)] == [
        "lod_spec", "facts", "visible_fact_keys_by_lod",
    ]
    with pytest.raises(FrozenInstanceError):
        content.facts = ()


@pytest.mark.parametrize("facts", [[], [WorldFact("a", "one")], ("bad",)])
def test_content_rejects_mutable_or_wrong_fact_containers(facts):
    with pytest.raises(ValueError):
        _content(facts=facts)


def test_content_allows_empty_facts_for_generic_model():
    content = _content(facts=(), levels=((), ()))
    assert content.facts == ()


def test_content_rejects_duplicate_fact_keys():
    with pytest.raises(ValueError, match="duplicate fact key"):
        _content(facts=(WorldFact("a", "1"), WorldFact("a", "2")))


@pytest.mark.parametrize("levels", [
    [["a"], ["a", "b"]],
    (["a"], ("a", "b")),
    (("a",),),
    (("a",), ("a", "b"), ("a", "b")),
])
def test_content_rejects_invalid_visible_level_containers_or_count(levels):
    with pytest.raises(ValueError):
        _content(levels=levels)


@pytest.mark.parametrize("bad_key", ["", " ", " a", "a ", 1, None])
def test_content_rejects_invalid_visible_keys(bad_key):
    with pytest.raises(ValueError):
        _content(levels=((bad_key,), (bad_key, "b")))


def test_content_rejects_duplicate_unknown_and_non_cumulative_keys():
    with pytest.raises(ValueError, match="duplicate visible"):
        _content(levels=(("a", "a"), ("a", "b")))
    with pytest.raises(ValueError, match="unknown visible"):
        _content(levels=(("missing",), ("missing", "a")))
    with pytest.raises(ValueError, match="cumulative"):
        _content(levels=(("a",), ("b",)))


def test_generic_content_does_not_require_all_facts_at_final_lod():
    content = _content(levels=((), ("a",)))
    assert _keys(fact_partition_for_lod(content, 1).hidden) == ("b",)


@pytest.mark.parametrize("lod", [-1, 2, True, False, 1.0, "1", None])
def test_lod_apis_reject_invalid_indices_without_clamping(lod):
    with pytest.raises(ValueError):
        fact_partition_for_lod(_content(), lod)
    with pytest.raises(ValueError):
        visible_facts_for_lod(_content(), lod)


def test_partition_is_pure_ordered_complete_and_reuses_world_contract():
    content = _content()
    before = content
    result = fact_partition_for_lod(content, 0)
    assert _keys(result.visible) == ("a",)
    assert _keys(result.hidden) == ("b",)
    assert result == partition_world_object_facts(
        content.facts, visible_fact_keys=("a",),
    )
    assert content == before


def test_visible_projection_contains_no_hidden_or_content_metadata():
    content = _content()
    result = visible_facts_for_lod(content, 0)
    assert result == VisibleWorldObjectFacts((WorldFact("a", "one"),))
    assert [field.name for field in fields(result)] == ["facts"]
    assert content == _content()


def test_goblin_well_identity_spec_and_authoritative_facts():
    content = GOBLIN_WELL_LOD_CONTENT
    assert serialize_world_object_id(content.lod_spec.object_id) == (
        "goblin:location/well"
    )
    assert content.lod_spec.attention_thresholds == (0, 1, 3, 6)
    assert content.lod_spec.max_lod == 3
    assert tuple((fact.key, fact.value) for fact in content.facts) == (
        ("shape", "well_like"),
        ("material", "stone"),
        ("age", "old"),
        ("pulley", "recent"),
        ("rope", "worn"),
        ("mark", "faded_emblem"),
    )


@pytest.mark.parametrize("lod, visible, hidden", [
    (0, ("shape",), ("material", "age", "pulley", "rope", "mark")),
    (1, ("shape", "material", "age"), ("pulley", "rope", "mark")),
    (2, ("shape", "material", "age", "pulley", "rope"), ("mark",)),
    (3, ("shape", "material", "age", "pulley", "rope", "mark"), ()),
])
def test_goblin_well_lod_partitions(lod, visible, hidden):
    partition = fact_partition_for_lod(GOBLIN_WELL_LOD_CONTENT, lod)
    assert _keys(partition.visible) == visible
    assert _keys(partition.hidden) == hidden
    assert _keys(visible_facts_for_lod(GOBLIN_WELL_LOD_CONTENT, lod).facts) == visible


def test_content_lookup_is_exact_and_has_no_fallback():
    well = WorldObjectId("goblin", "location/well")
    assert lod_content_for_world_object(well) is GOBLIN_WELL_LOD_CONTENT
    assert lod_content_for_world_object(WorldObjectId("goblin", "location/other")) is None
    assert lod_content_for_world_object(WorldObjectId("other", "location/well")) is None
    assert lod_content_for_world_object(WorldObjectId("goblin", "location/well-mark")) is None
    with pytest.raises(ValueError):
        lod_content_for_world_object("goblin:location/well")


def test_yaml_catalog_adapter_preserves_every_fact_and_cumulative_lod():
    for knowledge_object in goblin_knowledge_catalog().objects:
        content = lod_content_for_world_object(knowledge_object.object_id)
        assert tuple((fact.key, fact.value) for fact in content.facts) == tuple(
            (fact.key, fact.value) for fact in knowledge_object.facts
        )
        assert content.visible_fact_keys_by_lod == tuple(
            tuple(fact.key for fact in knowledge_object.facts if fact.lod <= lod)
            for lod in range(4)
        )


@pytest.mark.parametrize("attention, cap, lod, keys", [
    (0, 3, 0, ("shape",)),
    (1, 3, 1, ("shape", "material", "age")),
    (3, 3, 2, ("shape", "material", "age", "pulley", "rope")),
    (6, 3, 3, ("shape", "material", "age", "pulley", "rope", "mark")),
    (6, 1, 1, ("shape", "material", "age")),
    (6, 2, 2, ("shape", "material", "age", "pulley", "rope")),
    (2, 3, 1, ("shape", "material", "age")),
])
def test_attention_and_cap_compose_before_content_query(attention, cap, lod, keys):
    content = GOBLIN_WELL_LOD_CONTENT
    attention_state = ObjectAttentionState(attention)
    lod_state = ObjectLodState(cap)
    current = derive_current_lod(content.lod_spec, attention_state, lod_state)
    assert current == lod
    assert _keys(visible_facts_for_lod(content, current).facts) == keys
    assert attention_state == ObjectAttentionState(attention)
    assert lod_state == ObjectLodState(cap)


def test_d2_transition_composes_without_storing_current_lod():
    content = GOBLIN_WELL_LOD_CONTENT
    attention = ObjectAttentionState(0)
    levels = []
    for update in (attention_after_observe, attention_after_inspect,
                   attention_after_observe, attention_after_inspect):
        previous = attention
        attention = update(attention)
        lod = derive_current_lod(content.lod_spec, attention, ObjectLodState(3))
        levels.append((attention.attention_level, lod,
                       _keys(visible_facts_for_lod(content, lod).facts)))
        assert previous != attention
    assert [entry[:2] for entry in levels] == [(1, 1), (3, 2), (4, 2), (6, 3)]
    assert not hasattr(content, "current_lod")
    assert not hasattr(content, "attention")
    assert not hasattr(content, "lod_state")
