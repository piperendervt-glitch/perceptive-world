"""Authoritative headless application of canonical spatial actions."""

from .input_actions import MovePlayerToPositionAction
from .spatial import PlayerPosition, SceneCell, can_player_occupy
from .spatial_content import spatial_exit_at_cell


def apply_player_movement(state, action: MovePlayerToPositionAction) -> None:
    if type(action) is not MovePlayerToPositionAction:
        raise ValueError("action must be a MovePlayerToPositionAction")
    definition = state.spatial_definition_for_location(state.location)
    story_definition = (
        state.story_spatial_definition_for_node(state.node)
        if state.story_spatial_active else None
    )
    if story_definition is not None:
        definition = story_definition
    if definition is None:
        raise ValueError("current location has no spatial definition")
    current = state.player_position
    if type(current) is not PlayerPosition:
        raise ValueError("current player_position is required")
    if not can_player_occupy(definition.spec, current):
        raise ValueError("current player_position is not occupiable")
    destination = action.destination
    if abs(destination.x - current.x) + abs(destination.y - current.y) != 1:
        raise ValueError("destination must be exactly one cardinal step away")
    if not can_player_occupy(definition.spec, destination):
        raise ValueError("destination is not occupiable")
    if story_definition is not None:
        from .story_spatial import story_trigger_at_cell
        if story_trigger_at_cell(
            story_definition, SceneCell(destination.x, destination.y),
        ) is not None:
            raise ValueError("trigger cell requires a story choice action")
    elif spatial_exit_at_cell(definition, SceneCell(destination.x, destination.y)) is not None:
        raise ValueError("exit cell requires a scene transition action")
    state.player_position = destination
