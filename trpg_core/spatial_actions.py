"""Authoritative headless application of canonical spatial actions."""

from .input_actions import MovePlayerToPositionAction
from .spatial import PlayerPosition, can_player_occupy
from .spatial_content import spatial_definition_for_scene


def apply_player_movement(state, action: MovePlayerToPositionAction) -> None:
    if type(action) is not MovePlayerToPositionAction:
        raise ValueError("action must be a MovePlayerToPositionAction")
    definition = spatial_definition_for_scene(state.location)
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
    state.player_position = destination
