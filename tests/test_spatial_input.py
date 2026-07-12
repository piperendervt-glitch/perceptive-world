import pytest

from trpg_core.input_actions import MovePlayerToPositionAction
from trpg_core.spatial import MovementStep, PlayerPosition
from trpg_core.spatial_input import (
    movement_action_from_step,
    movement_step_for_gamepad_code,
    movement_step_for_keyboard_code,
    movement_step_for_line_command,
)


@pytest.mark.parametrize("code,expected", [
    ("KeyW", (0, -1)), ("ArrowUp", (0, -1)),
    ("KeyD", (1, 0)), ("ArrowRight", (1, 0)),
    ("KeyS", (0, 1)), ("ArrowDown", (0, 1)),
    ("KeyA", (-1, 0)), ("ArrowLeft", (-1, 0)),
])
def test_keyboard_codes_map_exactly(code, expected):
    assert movement_step_for_keyboard_code(code) == MovementStep(*expected)


@pytest.mark.parametrize("code,expected", [
    ("DPadUp", (0, -1)), ("DPadRight", (1, 0)),
    ("DPadDown", (0, 1)), ("DPadLeft", (-1, 0)),
])
def test_gamepad_codes_map_exactly(code, expected):
    assert movement_step_for_gamepad_code(code) == MovementStep(*expected)


@pytest.mark.parametrize("resolver,code", [
    (movement_step_for_keyboard_code, "keyw"),
    (movement_step_for_keyboard_code, " KeyW"),
    (movement_step_for_keyboard_code, "KeyW "),
    (movement_step_for_keyboard_code, "Unknown"),
    (movement_step_for_gamepad_code, "dpadup"),
    (movement_step_for_gamepad_code, " DPadUp"),
    (movement_step_for_gamepad_code, "Unknown"),
])
def test_physical_adapters_do_not_normalize(resolver, code):
    assert resolver(code) is None


@pytest.mark.parametrize("command,expected", [
    ("step north", (0, -1)), ("step east", (1, 0)),
    ("step south", (0, 1)), ("step west", (-1, 0)),
])
def test_line_commands_are_exact_and_distinct_from_go(command, expected):
    assert movement_step_for_line_command(command) == MovementStep(*expected)
    assert movement_step_for_line_command(command.upper()) is None
    assert movement_step_for_line_command(command + " ") is None
    assert movement_step_for_line_command(command.replace("step", "go")) is None


def test_action_construction_stores_only_resolved_destination_and_is_pure():
    position = PlayerPosition(1, 2)
    step = MovementStep(1, 0)
    action = movement_action_from_step(position, step)
    assert action == MovePlayerToPositionAction(PlayerPosition(2, 2))
    assert set(action.__dict__) == {"destination"}
    assert position == PlayerPosition(1, 2) and step == MovementStep(1, 0)
