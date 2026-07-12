"""Pure physical and line-input adapters for spatial movement."""

from .input_actions import DepartAction, MovePlayerToPositionAction, MoveToLocationAction
from .spatial import (
    DepartSceneExit, MovementStep, MoveToSceneExit, PlayerPosition, SceneCell,
    player_position_after_step,
)
from .spatial_content import SceneSpatialDefinition, spatial_exit_at_cell
from .world import WorldObjectId


_KEYBOARD_STEPS = {
    "KeyW": MovementStep(0, -1),
    "ArrowUp": MovementStep(0, -1),
    "KeyD": MovementStep(1, 0),
    "ArrowRight": MovementStep(1, 0),
    "KeyS": MovementStep(0, 1),
    "ArrowDown": MovementStep(0, 1),
    "KeyA": MovementStep(-1, 0),
    "ArrowLeft": MovementStep(-1, 0),
}

_GAMEPAD_STEPS = {
    "DPadUp": MovementStep(0, -1),
    "DPadRight": MovementStep(1, 0),
    "DPadDown": MovementStep(0, 1),
    "DPadLeft": MovementStep(-1, 0),
}

_LINE_STEPS = {
    "step north": MovementStep(0, -1),
    "step east": MovementStep(1, 0),
    "step south": MovementStep(0, 1),
    "step west": MovementStep(-1, 0),
}


def movement_step_for_keyboard_code(code: str) -> MovementStep | None:
    return _KEYBOARD_STEPS.get(code) if type(code) is str else None


def movement_step_for_gamepad_code(code: str) -> MovementStep | None:
    return _GAMEPAD_STEPS.get(code) if type(code) is str else None


def movement_step_for_line_command(command: str) -> MovementStep | None:
    return _LINE_STEPS.get(command) if type(command) is str else None


def movement_action_from_step(
    position: PlayerPosition,
    step: MovementStep,
) -> MovePlayerToPositionAction:
    if type(position) is not PlayerPosition:
        raise ValueError("position must be a PlayerPosition")
    if type(step) is not MovementStep:
        raise ValueError("step must be a MovementStep")
    return MovePlayerToPositionAction(player_position_after_step(position, step))


def canonical_action_for_spatial_step(
    *,
    current_scene_id: WorldObjectId,
    current_position: PlayerPosition,
    step: MovementStep,
    definition: SceneSpatialDefinition,
):
    if type(current_scene_id) is not WorldObjectId:
        raise ValueError("current_scene_id must be a WorldObjectId")
    if type(current_position) is not PlayerPosition:
        raise ValueError("current_position must be a PlayerPosition")
    if type(step) is not MovementStep:
        raise ValueError("step must be a MovementStep")
    if type(definition) is not SceneSpatialDefinition:
        raise ValueError("definition must be a SceneSpatialDefinition")
    candidate = player_position_after_step(current_position, step)
    exit_ = spatial_exit_at_cell(definition, SceneCell(candidate.x, candidate.y))
    if exit_ is None:
        return MovePlayerToPositionAction(candidate)
    if type(exit_.transition) is MoveToSceneExit:
        return MoveToLocationAction(exit_.transition.destination_scene_id)
    if type(exit_.transition) is DepartSceneExit:
        return DepartAction()
    raise ValueError("unsupported spatial exit transition")
