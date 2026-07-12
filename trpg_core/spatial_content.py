"""Closed production spatial definitions, independent of runtime and UI."""

from dataclasses import dataclass

from .spatial import (
    ObjectPosition,
    PlayerPosition,
    SceneBounds,
    SceneCell,
    SceneSpatialSpec,
    SpatialEntrySpawn,
    SpatialExit,
    SpatialObjectPlacement,
    can_player_occupy,
    is_walkable_cell,
)
from .world import WorldObjectId


@dataclass(frozen=True)
class SceneSpatialDefinition:
    spec: SceneSpatialSpec
    player_spawn: PlayerPosition
    entry_spawns: tuple[SpatialEntrySpawn, ...] = ()
    exits: tuple[SpatialExit, ...] = ()

    def __post_init__(self) -> None:
        if type(self.spec) is not SceneSpatialSpec:
            raise ValueError("spec must be a SceneSpatialSpec")
        if type(self.player_spawn) is not PlayerPosition:
            raise ValueError("player_spawn must be a PlayerPosition")
        if not can_player_occupy(self.spec, self.player_spawn):
            raise ValueError("player_spawn must be occupiable")
        if type(self.entry_spawns) is not tuple:
            raise ValueError("entry_spawns must be a tuple")
        if type(self.exits) is not tuple:
            raise ValueError("exits must be a tuple")

        source_ids: set[WorldObjectId] = set()
        entry_positions: set[PlayerPosition] = set()
        for entry in self.entry_spawns:
            if type(entry) is not SpatialEntrySpawn:
                raise ValueError("entry spawn must be a SpatialEntrySpawn")
            if entry.source_scene_id in source_ids:
                raise ValueError("duplicate entry source scene ID")
            if entry.position in entry_positions:
                raise ValueError("duplicate entry position")
            if not can_player_occupy(self.spec, entry.position):
                raise ValueError("entry position must be walkable and unblocked")
            source_ids.add(entry.source_scene_id)
            entry_positions.add(entry.position)

        exit_cells: set[SceneCell] = set()
        object_cells = {
            SceneCell(placement.position.x, placement.position.y)
            for placement in self.spec.object_placements
        }
        for exit_ in self.exits:
            if type(exit_) is not SpatialExit:
                raise ValueError("exit must be a SpatialExit")
            if exit_.cell in exit_cells:
                raise ValueError("duplicate exit cell")
            if not is_walkable_cell(self.spec, exit_.cell):
                raise ValueError("exit cell must be walkable")
            if exit_.cell in object_cells:
                raise ValueError("exit cell must not overlap an object")
            if PlayerPosition(exit_.cell.x, exit_.cell.y) in entry_positions:
                raise ValueError("entry position must not overlap an exit cell")
            exit_cells.add(exit_.cell)


def scene_world_object_id(definition: SceneSpatialDefinition) -> WorldObjectId:
    if type(definition) is not SceneSpatialDefinition:
        raise ValueError("definition must be a SceneSpatialDefinition")
    expected_local_id = f"location/{definition.spec.scene_id}"
    matches = tuple(
        placement.object_id
        for placement in definition.spec.object_placements
        if placement.object_id.local_id == expected_local_id
    )
    if len(matches) != 1:
        raise ValueError("definition must contain its exact scene object")
    return matches[0]


def entry_spawn_from_scene(
    definition: SceneSpatialDefinition,
    source_scene_id: WorldObjectId,
) -> PlayerPosition | None:
    if type(definition) is not SceneSpatialDefinition:
        raise ValueError("definition must be a SceneSpatialDefinition")
    if type(source_scene_id) is not WorldObjectId:
        raise ValueError("source_scene_id must be a WorldObjectId")
    entry = next(
        (entry for entry in definition.entry_spawns
         if entry.source_scene_id == source_scene_id),
        None,
    )
    return entry.position if entry is not None else None


def spatial_exit_at_cell(
    definition: SceneSpatialDefinition,
    cell: SceneCell,
) -> SpatialExit | None:
    if type(definition) is not SceneSpatialDefinition:
        raise ValueError("definition must be a SceneSpatialDefinition")
    if type(cell) is not SceneCell:
        raise ValueError("cell must be a SceneCell")
    return next((exit_ for exit_ in definition.exits if exit_.cell == cell), None)


_WELL_DEFINITION = SceneSpatialDefinition(
    spec=SceneSpatialSpec(
        scene_id="well",
        bounds=SceneBounds(7, 5),
        walkable_cells=tuple(
            SceneCell(x, y)
            for y in range(1, 4)
            for x in range(1, 6)
        ),
        object_placements=(SpatialObjectPlacement(
            object_id=WorldObjectId("goblin", "location/well"),
            position=ObjectPosition(3, 2),
            blocks_movement=True,
        ),),
    ),
    player_spawn=PlayerPosition(1, 2),
)

_DEFINITIONS = (_WELL_DEFINITION,)


def legacy_spatial_definition_for_scene(
    scenario_id: str,
    scene_id: str | None = None,
) -> SceneSpatialDefinition | None:
    if scene_id is None:
        scene_id = scenario_id
        scenario_id = "goblin"
    if scenario_id != "goblin":
        return None
    if type(scene_id) is not str:
        raise ValueError("scene_id must be a string")
    return next(
        (definition for definition in _DEFINITIONS
         if definition.spec.scene_id == scene_id),
        None,
    )


def current_spatial_definition_for_scene(
    scenario_id: str,
    scene_id: str,
) -> SceneSpatialDefinition | None:
    if type(scenario_id) is not str or not scenario_id:
        raise ValueError("scenario_id must be a non-empty string")
    if type(scene_id) is not str:
        raise ValueError("scene_id must be a string")
    if scenario_id != "goblin" or not scene_id:
        return None
    from .spatial_catalog import (
        goblin_scene_spatial_catalog,
        spatial_definition_in_catalog,
    )
    return spatial_definition_in_catalog(
        goblin_scene_spatial_catalog(),
        WorldObjectId(scenario_id, f"location/{scene_id}"),
    )


def spatial_definition_for_scene(scene_id: str) -> SceneSpatialDefinition | None:
    """Current goblin live lookup; retained as the simple content query API."""
    return current_spatial_definition_for_scene("goblin", scene_id)
