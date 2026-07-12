"""Closed spatial content catalog, deliberately disconnected from live runtime."""

from dataclasses import dataclass

from .spatial import (
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
)
from .spatial_content import (
    SceneSpatialDefinition,
    entry_spawn_from_scene,
    scene_world_object_id,
)
from .world import WorldObjectId


@dataclass(frozen=True)
class SceneSpatialCatalog:
    definitions: tuple[SceneSpatialDefinition, ...]

    def __post_init__(self) -> None:
        if type(self.definitions) is not tuple:
            raise ValueError("definitions must be a tuple")
        scene_ids: set[WorldObjectId] = set()
        for definition in self.definitions:
            if type(definition) is not SceneSpatialDefinition:
                raise ValueError("catalog entry must be a SceneSpatialDefinition")
            scene_id = scene_world_object_id(definition)
            if scene_id in scene_ids:
                raise ValueError("duplicate catalog scene ID")
            scene_ids.add(scene_id)


def spatial_definition_in_catalog(
    catalog: SceneSpatialCatalog,
    scene_id: WorldObjectId,
) -> SceneSpatialDefinition | None:
    if type(catalog) is not SceneSpatialCatalog:
        raise ValueError("catalog must be a SceneSpatialCatalog")
    if type(scene_id) is not WorldObjectId:
        raise ValueError("scene_id must be a WorldObjectId")
    return next(
        (definition for definition in catalog.definitions
         if scene_world_object_id(definition) == scene_id),
        None,
    )


def validate_spatial_catalog_topology(catalog: SceneSpatialCatalog) -> None:
    if type(catalog) is not SceneSpatialCatalog:
        raise ValueError("catalog must be a SceneSpatialCatalog")
    scene_ids = {
        scene_world_object_id(definition) for definition in catalog.definitions
    }
    for definition in catalog.definitions:
        source_scene_id = scene_world_object_id(definition)
        for entry in definition.entry_spawns:
            if entry.source_scene_id not in scene_ids:
                raise ValueError("entry source scene is not in catalog")
        for exit_ in definition.exits:
            transition = exit_.transition
            if type(transition) is DepartSceneExit:
                continue
            destination = spatial_definition_in_catalog(
                catalog, transition.destination_scene_id,
            )
            if destination is None:
                raise ValueError("exit destination scene is not in catalog")
            if entry_spawn_from_scene(destination, source_scene_id) is None:
                raise ValueError("exit destination has no entry for source scene")


def _scene_id(local_id: str) -> WorldObjectId:
    return WorldObjectId("goblin", f"location/{local_id}")


def _walkable_cells(exit_cells: tuple[SceneCell, ...]) -> tuple[SceneCell, ...]:
    interior = tuple(
        SceneCell(x, y) for y in range(1, 4) for x in range(1, 6)
    )
    return interior + exit_cells


def _definition(
    scene_id: str,
    player_spawn: PlayerPosition,
    landmark_position: ObjectPosition,
    blocks_movement: bool,
    entry_spawns: tuple[SpatialEntrySpawn, ...],
    exits: tuple[SpatialExit, ...],
) -> SceneSpatialDefinition:
    return SceneSpatialDefinition(
        spec=SceneSpatialSpec(
            scene_id=scene_id,
            bounds=SceneBounds(7, 5),
            walkable_cells=_walkable_cells(tuple(exit_.cell for exit_ in exits)),
            object_placements=(SpatialObjectPlacement(
                object_id=_scene_id(scene_id),
                position=landmark_position,
                blocks_movement=blocks_movement,
            ),),
        ),
        player_spawn=player_spawn,
        entry_spawns=entry_spawns,
        exits=exits,
    )


_PLAZA = _definition(
    "plaza", PlayerPosition(3, 2), ObjectPosition(4, 2), False,
    (
        SpatialEntrySpawn(_scene_id("well"), PlayerPosition(3, 1)),
        SpatialEntrySpawn(_scene_id("herbhut"), PlayerPosition(5, 2)),
        SpatialEntrySpawn(_scene_id("shrine"), PlayerPosition(3, 3)),
        SpatialEntrySpawn(_scene_id("elderhouse"), PlayerPosition(1, 2)),
    ),
    (
        SpatialExit(SceneCell(3, 0), MoveToSceneExit(_scene_id("well"))),
        SpatialExit(SceneCell(6, 2), MoveToSceneExit(_scene_id("herbhut"))),
        SpatialExit(SceneCell(3, 4), MoveToSceneExit(_scene_id("shrine"))),
        SpatialExit(SceneCell(0, 2), MoveToSceneExit(_scene_id("elderhouse"))),
    ),
)

_WELL = _definition(
    "well", PlayerPosition(1, 2), ObjectPosition(3, 2), True,
    (
        SpatialEntrySpawn(_scene_id("plaza"), PlayerPosition(3, 3)),
        SpatialEntrySpawn(_scene_id("lookout"), PlayerPosition(3, 1)),
    ),
    (
        SpatialExit(SceneCell(3, 4), MoveToSceneExit(_scene_id("plaza"))),
        SpatialExit(SceneCell(3, 0), MoveToSceneExit(_scene_id("lookout"))),
    ),
)

_LOOKOUT = _definition(
    "lookout", PlayerPosition(2, 2), ObjectPosition(3, 2), True,
    (SpatialEntrySpawn(_scene_id("well"), PlayerPosition(3, 3)),),
    (SpatialExit(SceneCell(3, 4), MoveToSceneExit(_scene_id("well"))),),
)

_HERBHUT = _definition(
    "herbhut", PlayerPosition(2, 2), ObjectPosition(3, 2), True,
    (SpatialEntrySpawn(_scene_id("plaza"), PlayerPosition(1, 2)),),
    (SpatialExit(SceneCell(0, 2), MoveToSceneExit(_scene_id("plaza"))),),
)

_SHRINE = _definition(
    "shrine", PlayerPosition(2, 2), ObjectPosition(3, 2), True,
    (SpatialEntrySpawn(_scene_id("plaza"), PlayerPosition(3, 1)),),
    (SpatialExit(SceneCell(3, 0), MoveToSceneExit(_scene_id("plaza"))),),
)

_ELDERHOUSE = _definition(
    "elderhouse", PlayerPosition(3, 1), ObjectPosition(3, 2), True,
    (
        SpatialEntrySpawn(_scene_id("plaza"), PlayerPosition(5, 2)),
        SpatialEntrySpawn(_scene_id("forest_gate"), PlayerPosition(1, 2)),
    ),
    (
        SpatialExit(SceneCell(6, 2), MoveToSceneExit(_scene_id("plaza"))),
        SpatialExit(SceneCell(0, 2), MoveToSceneExit(_scene_id("forest_gate"))),
    ),
)

_FOREST_GATE = _definition(
    "forest_gate", PlayerPosition(3, 2), ObjectPosition(2, 2), True,
    (SpatialEntrySpawn(_scene_id("elderhouse"), PlayerPosition(5, 2)),),
    (
        SpatialExit(SceneCell(6, 2), MoveToSceneExit(_scene_id("elderhouse"))),
        SpatialExit(SceneCell(3, 0), DepartSceneExit()),
    ),
)

_GOBLIN_CATALOG = SceneSpatialCatalog((
    _PLAZA,
    _WELL,
    _LOOKOUT,
    _HERBHUT,
    _SHRINE,
    _ELDERHOUSE,
    _FOREST_GATE,
))
validate_spatial_catalog_topology(_GOBLIN_CATALOG)


def goblin_scene_spatial_catalog() -> SceneSpatialCatalog:
    return _GOBLIN_CATALOG
