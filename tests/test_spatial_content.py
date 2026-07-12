import dataclasses

import pytest

from trpg_core.spatial import (
    MoveToSceneExit,
    ObjectPosition,
    PlayerPosition,
    SceneCell,
    SpatialEntrySpawn,
    SpatialExit,
    can_player_occupy,
)
from trpg_core.spatial_content import (
    SceneSpatialDefinition,
    entry_spawn_from_scene,
    spatial_definition_for_scene,
    spatial_exit_at_cell,
)
from trpg_core.world import WorldObjectId


def test_well_definition_is_exact_immutable_production_geometry():
    definition = spatial_definition_for_scene("well")
    assert definition is not None
    assert definition.spec.scene_id == "well"
    assert (definition.spec.bounds.width, definition.spec.bounds.height) == (7, 5)
    assert definition.player_spawn == PlayerPosition(1, 2)
    assert len(definition.spec.walkable_cells) == 15
    placement, = definition.spec.object_placements
    assert placement.object_id == WorldObjectId("goblin", "location/well")
    assert placement.position == ObjectPosition(3, 2)
    assert placement.blocks_movement is True
    assert can_player_occupy(definition.spec, definition.player_spawn)
    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.player_spawn = PlayerPosition(2, 2)


@pytest.mark.parametrize("scene_id", ["", "wel", "location/well", "古井戸", "well/extra"])
def test_scene_lookup_has_no_fallback(scene_id):
    assert spatial_definition_for_scene(scene_id) is None


def test_definition_has_only_domain_fields_and_strict_types():
    definition = spatial_definition_for_scene("well")
    assert {field.name for field in dataclasses.fields(definition)} == {
        "spec", "player_spawn", "entry_spawns", "exits",
    }
    assert definition.entry_spawns == ()
    assert definition.exits == ()
    with pytest.raises(ValueError):
        SceneSpatialDefinition({}, PlayerPosition(1, 2))
    with pytest.raises(ValueError):
        SceneSpatialDefinition(definition.spec, (1, 2))
    with pytest.raises(ValueError):
        SceneSpatialDefinition(definition.spec, PlayerPosition(3, 2))


def test_definition_validates_entry_exit_aggregates_and_exact_queries():
    base = spatial_definition_for_scene("well")
    plaza = WorldObjectId("goblin", "location/plaza")
    lookout = WorldObjectId("goblin", "location/lookout")
    entry = SpatialEntrySpawn(plaza, PlayerPosition(2, 1))
    exit_ = SpatialExit(SceneCell(5, 2), MoveToSceneExit(lookout))
    definition = SceneSpatialDefinition(
        base.spec, base.player_spawn, (entry,), (exit_,),
    )
    assert entry_spawn_from_scene(definition, plaza) == PlayerPosition(2, 1)
    assert entry_spawn_from_scene(
        definition, WorldObjectId("other", "location/plaza"),
    ) is None
    assert spatial_exit_at_cell(definition, SceneCell(5, 2)) == exit_
    assert spatial_exit_at_cell(definition, SceneCell(4, 2)) is None


@pytest.mark.parametrize("entries,exits", [
    ([], ()),
    ((), []),
    (("entry",), ()),
    ((), ("exit",)),
])
def test_definition_rejects_non_tuple_or_wrong_entry_exit_values(entries, exits):
    base = spatial_definition_for_scene("well")
    with pytest.raises(ValueError):
        SceneSpatialDefinition(base.spec, base.player_spawn, entries, exits)


def test_spatial_content_has_no_renderer_metadata():
    definition = spatial_definition_for_scene("well")
    names = {field.name for field in dataclasses.fields(definition.spec)}
    assert not {"sprite", "color", "panel", "pixel", "renderer"} & names
