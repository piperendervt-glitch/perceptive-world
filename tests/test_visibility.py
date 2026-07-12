import dataclasses

import pytest

from trpg_core.map import GameMap, Location, build_map
from trpg_core.scenario_loader import load_scenario
from trpg_core.world import (
    SceneWorldObject,
    VisibleWorldObjectFacts,
    WorldFact,
    WorldObjectFactPartition,
    WorldObjectId,
    WorldObjectSpec,
    WorldObjectVisibility,
    focusable_world_object_ids,
    focusable_world_object_ids_for_current_location,
    partition_world_object_facts,
    serialize_world_object_id,
    validate_scene_world_objects,
    world_objects_for_current_scene,
)


def _spec(local_id="object/a", *, scene_id="well"):
    return WorldObjectSpec(
        WorldObjectId("goblin", local_id), "prop", local_id, scene_id,
    )


def _scene(spec, visibility):
    return SceneWorldObject(spec, visibility, VisibleWorldObjectFacts())


@pytest.mark.parametrize("values", [
    (False, False, False),
    (True, False, False),
    (True, True, False),
    (True, True, True),
])
def test_visibility_represents_each_valid_state_and_is_frozen(values):
    visibility = WorldObjectVisibility(*values)
    assert dataclasses.astuple(visibility) == values
    with pytest.raises(dataclasses.FrozenInstanceError):
        visibility.perceived = False


@pytest.mark.parametrize("values", [
    (False, True, False),
    (False, False, True),
    (False, True, True),
    (True, False, True),
])
def test_visibility_rejects_invalid_combinations(values):
    with pytest.raises(ValueError):
        WorldObjectVisibility(*values)


@pytest.mark.parametrize("field", range(3))
def test_visibility_rejects_non_bool(field):
    values = [True, True, True]
    values[field] = 1
    with pytest.raises(ValueError, match="bool"):
        WorldObjectVisibility(*values)


def test_world_fact_is_frozen_and_requires_stable_key_and_string_value():
    fact = WorldFact("shape", "well_like")
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.key = "other"
    for key in ("", " ", " shape"):
        with pytest.raises(ValueError):
            WorldFact(key, "value")
    with pytest.raises(ValueError):
        WorldFact("shape", 1)


def test_fact_partition_is_complete_disjoint_ordered_and_public_safe():
    facts = (
        WorldFact("shape", "well_like"),
        WorldFact("material", "stone"),
        WorldFact("mark", "faded_emblem"),
    )
    before = tuple(facts)
    result = partition_world_object_facts(
        facts, visible_fact_keys=("shape", "material"),
    )
    assert isinstance(result, WorldObjectFactPartition)
    assert tuple(f.key for f in result.visible) == ("shape", "material")
    assert tuple(f.key for f in result.hidden) == ("mark",)
    assert result.visible + result.hidden == facts
    assert facts == before
    public = VisibleWorldObjectFacts(result.visible)
    assert tuple(f.key for f in public.facts) == ("shape", "material")
    assert not hasattr(public, "hidden") and not hasattr(public, "all_facts")
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.hidden = ()


def test_fact_projection_models_copy_mutable_inputs():
    visible = [WorldFact("shape", "well_like")]
    hidden = [WorldFact("mark", "faded_emblem")]
    partition = WorldObjectFactPartition(visible, hidden)
    public = VisibleWorldObjectFacts(visible)
    visible.clear()
    hidden.clear()
    assert tuple(f.key for f in partition.visible) == ("shape",)
    assert tuple(f.key for f in partition.hidden) == ("mark",)
    assert tuple(f.key for f in public.facts) == ("shape",)


def test_fact_partition_handles_empty_none_visible_and_all_visible():
    assert partition_world_object_facts((), visible_fact_keys=()) == (
        WorldObjectFactPartition((), ())
    )
    facts = (WorldFact("shape", "well_like"), WorldFact("material", "stone"))
    assert partition_world_object_facts(facts, visible_fact_keys=()).hidden == facts
    assert partition_world_object_facts(
        facts, visible_fact_keys=("shape", "material"),
    ).visible == facts


def test_fact_partition_rejects_duplicate_and_unknown_keys():
    fact = WorldFact("shape", "well_like")
    with pytest.raises(ValueError, match="duplicate fact"):
        partition_world_object_facts((fact, fact), visible_fact_keys=())
    with pytest.raises(ValueError, match="duplicate visible"):
        partition_world_object_facts((fact,), visible_fact_keys=("shape", "shape"))
    with pytest.raises(ValueError, match="unknown visible"):
        partition_world_object_facts((fact,), visible_fact_keys=("mark",))


def test_scene_query_is_deterministic_frozen_and_preserves_map_state():
    scenario = load_scenario("goblin")
    game_map = build_map(scenario, "well")
    before = (game_map.current, tuple(game_map.locations), dict(game_map.here().exits))
    first = world_objects_for_current_scene(scenario_id="goblin", game_map=game_map)
    second = world_objects_for_current_scene(scenario_id="goblin", game_map=game_map)
    assert first == second
    assert isinstance(first, tuple)
    assert tuple(serialize_world_object_id(item.spec.object_id) for item in first) == (
        "goblin:location/well",
    )
    assert all(item.visibility == WorldObjectVisibility(True, True, True) for item in first)
    assert all(item.visible_facts.facts == () for item in first)
    assert (game_map.current, tuple(game_map.locations), dict(game_map.here().exits)) == before
    with pytest.raises(dataclasses.FrozenInstanceError):
        first[0].visibility = WorldObjectVisibility(True, True, False)


def test_scene_query_handles_no_map_and_rejects_invalid_current():
    assert world_objects_for_current_scene(scenario_id="goblin", game_map=None) == ()
    game_map = GameMap(
        locations={"well": Location("well", "古井戸")}, current="missing",
    )
    with pytest.raises(ValueError, match="current"):
        world_objects_for_current_scene(scenario_id="goblin", game_map=game_map)


def test_scene_object_validation_rejects_duplicate_and_foreign_scenario():
    item = _scene(_spec(), WorldObjectVisibility(True, True, True))
    with pytest.raises(ValueError, match="duplicate"):
        validate_scene_world_objects((item, item), scenario_id="goblin")
    foreign = _scene(
        WorldObjectSpec(WorldObjectId("envoy", "object/a"), "prop", "a", "well"),
        WorldObjectVisibility(True, True, True),
    )
    with pytest.raises(ValueError, match="another scenario"):
        validate_scene_world_objects((foreign,), scenario_id="goblin")


def test_focus_extraction_uses_visibility_and_stable_id_order():
    items = (
        _scene(_spec("object/z"), WorldObjectVisibility(True, True, True)),
        _scene(_spec("object/perceived"), WorldObjectVisibility(True, True, False)),
        _scene(_spec("object/unseen"), WorldObjectVisibility(True, False, False)),
        _scene(_spec("object/absent"), WorldObjectVisibility(False, False, False)),
        _scene(_spec("object/a"), WorldObjectVisibility(True, True, True)),
    )
    assert tuple(map(serialize_world_object_id, focusable_world_object_ids(
        items, scenario_id="goblin",
    ))) == ("goblin:object/a", "goblin:object/z")


def test_existing_focus_query_delegates_to_current_scene_semantics():
    scenario = load_scenario("goblin")
    game_map = build_map(scenario, "well")
    expected = tuple(
        item.spec.object_id
        for item in world_objects_for_current_scene(
            scenario_id=scenario.id, game_map=game_map,
        )
        if item.visibility.focus_candidate
    )
    assert focusable_world_object_ids_for_current_location(
        scenario.id, game_map,
    ) == expected
