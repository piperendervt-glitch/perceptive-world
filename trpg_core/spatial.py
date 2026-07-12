"""Pure, renderer-independent spatial domain contracts."""

from __future__ import annotations

from dataclasses import dataclass

from .world import WorldObjectId


def _require_int(value: object, field_name: str) -> None:
    if type(value) is not int:
        raise ValueError(f"{field_name} must be an int")


def _require_exact(value: object, expected_type: type, field_name: str) -> None:
    if type(value) is not expected_type:
        raise ValueError(f"{field_name} must be a {expected_type.__name__}")


@dataclass(frozen=True)
class SceneCell:
    x: int
    y: int

    def __post_init__(self) -> None:
        _require_int(self.x, "x")
        _require_int(self.y, "y")


@dataclass(frozen=True)
class PlayerPosition:
    x: int
    y: int

    def __post_init__(self) -> None:
        _require_int(self.x, "x")
        _require_int(self.y, "y")


@dataclass(frozen=True)
class SpatialEntrySpawn:
    source_scene_id: WorldObjectId
    position: PlayerPosition

    def __post_init__(self) -> None:
        _require_exact(self.source_scene_id, WorldObjectId, "source_scene_id")
        _require_exact(self.position, PlayerPosition, "position")


@dataclass(frozen=True)
class ObjectPosition:
    x: int
    y: int

    def __post_init__(self) -> None:
        _require_int(self.x, "x")
        _require_int(self.y, "y")


@dataclass(frozen=True)
class SceneBounds:
    width: int
    height: int

    def __post_init__(self) -> None:
        if type(self.width) is not int or self.width <= 0:
            raise ValueError("width must be a positive int")
        if type(self.height) is not int or self.height <= 0:
            raise ValueError("height must be a positive int")


@dataclass(frozen=True)
class MovementStep:
    dx: int
    dy: int

    def __post_init__(self) -> None:
        _require_int(self.dx, "dx")
        _require_int(self.dy, "dy")
        if (self.dx, self.dy) not in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            raise ValueError("movement step must be exactly one cardinal cell")


@dataclass(frozen=True)
class SpatialObjectPlacement:
    object_id: WorldObjectId
    position: ObjectPosition
    blocks_movement: bool

    def __post_init__(self) -> None:
        _require_exact(self.object_id, WorldObjectId, "object_id")
        _require_exact(self.position, ObjectPosition, "position")
        _require_exact(self.blocks_movement, bool, "blocks_movement")


@dataclass(frozen=True)
class MoveToSceneExit:
    destination_scene_id: WorldObjectId

    def __post_init__(self) -> None:
        _require_exact(
            self.destination_scene_id, WorldObjectId, "destination_scene_id",
        )


@dataclass(frozen=True)
class DepartSceneExit:
    pass


SpatialExitTransition = MoveToSceneExit | DepartSceneExit


@dataclass(frozen=True)
class SpatialExit:
    cell: SceneCell
    transition: SpatialExitTransition

    def __post_init__(self) -> None:
        _require_exact(self.cell, SceneCell, "cell")
        if type(self.transition) not in (MoveToSceneExit, DepartSceneExit):
            raise ValueError("transition must be a spatial exit transition")


@dataclass(frozen=True)
class SceneSpatialSpec:
    scene_id: str
    bounds: SceneBounds
    walkable_cells: tuple[SceneCell, ...]
    object_placements: tuple[SpatialObjectPlacement, ...]

    def __post_init__(self) -> None:
        if type(self.scene_id) is not str or not self.scene_id:
            raise ValueError("scene_id must be a non-empty string")
        _require_exact(self.bounds, SceneBounds, "bounds")
        _require_exact(self.walkable_cells, tuple, "walkable_cells")
        _require_exact(self.object_placements, tuple, "object_placements")
        if not self.walkable_cells:
            raise ValueError("walkable_cells must not be empty")

        seen_cells: set[SceneCell] = set()
        for cell in self.walkable_cells:
            _require_exact(cell, SceneCell, "walkable cell")
            if cell in seen_cells:
                raise ValueError("duplicate walkable cell")
            if not scene_bounds_contains(self.bounds, cell):
                raise ValueError("walkable cell must be within bounds")
            seen_cells.add(cell)

        seen_ids: set[WorldObjectId] = set()
        seen_positions: set[ObjectPosition] = set()
        for placement in self.object_placements:
            _require_exact(placement, SpatialObjectPlacement, "object placement")
            if placement.object_id in seen_ids:
                raise ValueError("duplicate object ID")
            if placement.position in seen_positions:
                raise ValueError("duplicate object position")
            if not scene_bounds_contains(
                self.bounds,
                SceneCell(placement.position.x, placement.position.y),
            ):
                raise ValueError("object position must be within bounds")
            seen_ids.add(placement.object_id)
            seen_positions.add(placement.position)


def scene_bounds_contains(bounds: SceneBounds, cell: SceneCell) -> bool:
    _require_exact(bounds, SceneBounds, "bounds")
    _require_exact(cell, SceneCell, "cell")
    return 0 <= cell.x < bounds.width and 0 <= cell.y < bounds.height


def player_position_after_step(
    position: PlayerPosition,
    step: MovementStep,
) -> PlayerPosition:
    _require_exact(position, PlayerPosition, "position")
    _require_exact(step, MovementStep, "step")
    return PlayerPosition(position.x + step.dx, position.y + step.dy)


def object_placement_for_world_object(
    spec: SceneSpatialSpec,
    object_id: WorldObjectId,
) -> SpatialObjectPlacement | None:
    _require_exact(spec, SceneSpatialSpec, "spec")
    _require_exact(object_id, WorldObjectId, "object_id")
    return next(
        (placement for placement in spec.object_placements
         if placement.object_id == object_id),
        None,
    )


def is_walkable_cell(spec: SceneSpatialSpec, cell: SceneCell) -> bool:
    _require_exact(spec, SceneSpatialSpec, "spec")
    _require_exact(cell, SceneCell, "cell")
    return scene_bounds_contains(spec.bounds, cell) and cell in spec.walkable_cells


def is_blocked_cell(spec: SceneSpatialSpec, cell: SceneCell) -> bool:
    _require_exact(spec, SceneSpatialSpec, "spec")
    _require_exact(cell, SceneCell, "cell")
    if not is_walkable_cell(spec, cell):
        return True
    return any(
        placement.blocks_movement
        and placement.position == ObjectPosition(cell.x, cell.y)
        for placement in spec.object_placements
    )


def can_player_occupy(spec: SceneSpatialSpec, position: PlayerPosition) -> bool:
    _require_exact(spec, SceneSpatialSpec, "spec")
    _require_exact(position, PlayerPosition, "position")
    return not is_blocked_cell(spec, SceneCell(position.x, position.y))
