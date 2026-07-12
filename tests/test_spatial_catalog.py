import dataclasses
from collections import deque

import pytest

from trpg_core.map import build_map
from trpg_core.scenario_loader import load_scenario
from trpg_core.spatial import (
    DepartSceneExit,
    MoveToSceneExit,
    ObjectPosition,
    PlayerPosition,
    SceneBounds,
    SceneCell,
    SceneSpatialSpec,
    SpatialEntrySpawn,
    SpatialExit,
    SpatialObjectPlacement,
    is_blocked_cell,
)
from trpg_core.spatial_catalog import (
    SceneSpatialCatalog,
    goblin_scene_spatial_catalog,
    spatial_definition_in_catalog,
    validate_spatial_catalog_topology,
)
from trpg_core.spatial_content import (
    SceneSpatialDefinition,
    entry_spawn_from_scene,
    scene_world_object_id,
    spatial_definition_for_scene,
    spatial_exit_at_cell,
)
from trpg_core.world import WorldObjectId


def _id(local_id):
    return WorldObjectId("test", f"location/{local_id}")


def _definition(scene_id, entries=(), exits=()):
    return SceneSpatialDefinition(
        SceneSpatialSpec(
            scene_id,
            SceneBounds(5, 4),
            tuple(SceneCell(x, y) for y in range(4) for x in range(5)),
            (SpatialObjectPlacement(
                _id(scene_id), ObjectPosition(2, 2), True,
            ),),
        ),
        PlayerPosition(1, 1),
        entries,
        exits,
    )


def test_catalog_is_strict_immutable_ordered_and_exactly_queried():
    first = _definition("first")
    second = _definition("second")
    catalog = SceneSpatialCatalog((first, second))
    assert catalog.definitions == (first, second)
    assert spatial_definition_in_catalog(catalog, _id("second")) is second
    assert spatial_definition_in_catalog(
        catalog, WorldObjectId("other", "location/second"),
    ) is None
    assert spatial_definition_in_catalog(catalog, _id("secon")) is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        catalog.definitions = ()
    for definitions in ([first], ("first",), (first, first)):
        with pytest.raises(ValueError):
            SceneSpatialCatalog(definitions)


def test_topology_accepts_move_entries_and_depart_without_reciprocal_rule():
    first = _definition(
        "first", (),
        (SpatialExit(SceneCell(4, 1), MoveToSceneExit(_id("second"))),),
    )
    second = _definition(
        "second",
        (SpatialEntrySpawn(_id("first"), PlayerPosition(1, 2)),),
        (SpatialExit(SceneCell(4, 1), DepartSceneExit()),),
    )
    validate_spatial_catalog_topology(SceneSpatialCatalog((first, second)))


def test_topology_rejects_missing_destination_entry_and_unknown_entry_source():
    first = _definition(
        "first", (),
        (SpatialExit(SceneCell(4, 1), MoveToSceneExit(_id("second"))),),
    )
    second = _definition("second")
    with pytest.raises(ValueError, match="no entry"):
        validate_spatial_catalog_topology(SceneSpatialCatalog((first, second)))
    missing = dataclasses.replace(
        first,
        exits=(SpatialExit(
            SceneCell(4, 1), MoveToSceneExit(_id("missing")),
        ),),
    )
    with pytest.raises(ValueError, match="not in catalog"):
        validate_spatial_catalog_topology(SceneSpatialCatalog((missing, second)))
    unknown_source = dataclasses.replace(
        second,
        entry_spawns=(SpatialEntrySpawn(
            _id("missing"), PlayerPosition(1, 2),
        ),),
    )
    with pytest.raises(ValueError, match="source scene"):
        validate_spatial_catalog_topology(
            SceneSpatialCatalog((first, unknown_source)),
        )


@pytest.mark.parametrize("entries,exits", [
    ((SpatialEntrySpawn(_id("first"), PlayerPosition(1, 2)),
      SpatialEntrySpawn(_id("first"), PlayerPosition(3, 2))), ()),
    ((SpatialEntrySpawn(_id("first"), PlayerPosition(1, 2)),
      SpatialEntrySpawn(_id("second"), PlayerPosition(1, 2))), ()),
    ((), (SpatialExit(SceneCell(4, 1), DepartSceneExit()),
          SpatialExit(SceneCell(4, 1), DepartSceneExit()))),
    ((SpatialEntrySpawn(_id("first"), PlayerPosition(4, 1)),),
     (SpatialExit(SceneCell(4, 1), DepartSceneExit()),)),
])
def test_definition_rejects_duplicate_and_overlapping_contracts(entries, exits):
    with pytest.raises(ValueError):
        _definition("scene", entries, exits)


@pytest.mark.parametrize("entry_position,exit_cell", [
    (PlayerPosition(5, 1), None),
    (PlayerPosition(2, 2), None),
    (None, SceneCell(5, 1)),
    (None, SceneCell(2, 2)),
])
def test_definition_rejects_outside_or_blocked_entry_exit(entry_position, exit_cell):
    entries = () if entry_position is None else (
        SpatialEntrySpawn(_id("source"), entry_position),
    )
    exits = () if exit_cell is None else (
        SpatialExit(exit_cell, DepartSceneExit()),
    )
    with pytest.raises(ValueError):
        _definition("scene", entries, exits)


def _reachable(definition, start):
    start_cell = SceneCell(start.x, start.y)
    visited = {start_cell}
    queue = deque((start_cell,))
    while queue:
        cell = queue.popleft()
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            neighbor = SceneCell(cell.x + dx, cell.y + dy)
            if neighbor not in visited and not is_blocked_cell(
                definition.spec, neighbor,
            ):
                visited.add(neighbor)
                queue.append(neighbor)
    return visited


def test_production_catalog_matches_goblin_game_map_and_is_connected():
    scenario = load_scenario("goblin")
    game_map = build_map(scenario)
    catalog = goblin_scene_spatial_catalog()
    expected_ids = tuple(game_map.locations)
    assert tuple(
        scene_world_object_id(definition).local_id.removeprefix("location/")
        for definition in catalog.definitions
    ) == expected_ids
    validate_spatial_catalog_topology(catalog)

    for definition in catalog.definitions:
        local_id = definition.spec.scene_id
        expected_destinations = set(game_map.locations[local_id].exits.values())
        actual_destinations = {
            exit_.transition.destination_scene_id.local_id.removeprefix("location/")
            for exit_ in definition.exits
            if type(exit_.transition) is MoveToSceneExit
        }
        assert actual_destinations == expected_destinations
        depart_count = sum(
            type(exit_.transition) is DepartSceneExit
            for exit_ in definition.exits
        )
        assert depart_count == int(game_map.locations[local_id].leads_to_adventure)
        assert scene_world_object_id(definition) == WorldObjectId(
            "goblin", f"location/{local_id}",
        )

        reachable = _reachable(definition, definition.player_spawn)
        targets = tuple(entry.position for entry in definition.entry_spawns)
        target_cells = {
            SceneCell(position.x, position.y) for position in targets
        } | {exit_.cell for exit_ in definition.exits}
        assert target_cells <= reachable
        for entry in definition.entry_spawns:
            assert {exit_.cell for exit_ in definition.exits} <= _reachable(
                definition, entry.position,
            )
        unblocked_walkable = {
            cell for cell in definition.spec.walkable_cells
            if not is_blocked_cell(definition.spec, cell)
        }
        assert unblocked_walkable == reachable


def test_production_queries_are_exact_and_live_lookup_remains_disconnected():
    catalog = goblin_scene_spatial_catalog()
    well_id = WorldObjectId("goblin", "location/well")
    catalog_well = spatial_definition_in_catalog(catalog, well_id)
    assert catalog_well is not None
    assert spatial_definition_in_catalog(
        catalog, WorldObjectId("other", "location/well"),
    ) is None
    active_well = spatial_definition_for_scene("well")
    assert active_well is not None
    assert active_well is not catalog_well
    assert active_well.entry_spawns == ()
    assert active_well.exits == ()
    assert spatial_definition_for_scene("plaza") is None
    assert entry_spawn_from_scene(
        catalog_well, WorldObjectId("goblin", "location/plaza"),
    ) == PlayerPosition(3, 3)
    assert spatial_exit_at_cell(catalog_well, SceneCell(3, 4)) is not None
