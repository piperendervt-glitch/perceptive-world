"""Closed production spatial definitions, independent of runtime and UI."""

from dataclasses import dataclass

from .spatial import (
    ObjectPosition,
    PlayerPosition,
    SceneBounds,
    SceneCell,
    SceneSpatialSpec,
    SpatialObjectPlacement,
    can_player_occupy,
)
from .world import WorldObjectId


@dataclass(frozen=True)
class SceneSpatialDefinition:
    spec: SceneSpatialSpec
    player_spawn: PlayerPosition

    def __post_init__(self) -> None:
        if type(self.spec) is not SceneSpatialSpec:
            raise ValueError("spec must be a SceneSpatialSpec")
        if type(self.player_spawn) is not PlayerPosition:
            raise ValueError("player_spawn must be a PlayerPosition")
        if not can_player_occupy(self.spec, self.player_spawn):
            raise ValueError("player_spawn must be occupiable")


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


def spatial_definition_for_scene(
    scene_id: str,
) -> SceneSpatialDefinition | None:
    if type(scene_id) is not str:
        raise ValueError("scene_id must be a string")
    return next(
        (definition for definition in _DEFINITIONS
         if definition.spec.scene_id == scene_id),
        None,
    )
