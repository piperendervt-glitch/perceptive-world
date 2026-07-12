"""最小入力モデルとpure resolverの境界テスト。"""

from __future__ import annotations

import copy
import dataclasses
import ast

import pytest

from dataclasses import FrozenInstanceError

from trpg_core.input_actions import (
    ClearFocusAction, DepartAction, ExploreAction, MoveToLocationAction,
    SetFocusAction, resolve_focus_command, resolve_move_action,
)
from trpg_core.world import WorldObjectId

from trpg_core.input_actions import (
    ApplyLodUnlockAction,
    DirectCommand,
    InspectFocusedObjectAction,
    MetaRequest,
    ObserveFocusedObjectAction,
    SelectMenuIndex,
    parse_raw_input,
    resolve_combat_command,
    resolve_direction,
    resolve_menu_index,
    resolve_meta_request,
)
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import GameState


def test_input_models_are_frozen_and_validate_values():
    values = (SelectMenuIndex(1), DirectCommand(" attack "), MetaRequest("status"))
    assert values[1].text == "attack"
    for value in values:
        assert value.__dataclass_params__.frozen
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, next(iter(value.__dict__)), "changed")
    with pytest.raises(ValueError):
        SelectMenuIndex(0)
    with pytest.raises(ValueError):
        DirectCommand(" ")
    with pytest.raises(ValueError):
        DirectCommand("1")
    with pytest.raises(ValueError):
        DirectCommand("help")


def test_canonical_lod_actions_are_frozen_and_separate_from_village_events():
    import typing
    from trpg_core.input_actions import VillageControllerEvent

    well = WorldObjectId("goblin", "location/well")
    actions = (ObserveFocusedObjectAction(), InspectFocusedObjectAction(),
               ApplyLodUnlockAction(well, 0))
    assert not actions[0].__dict__ and not actions[1].__dict__
    assert actions[2].object_id == well and actions[2].target_cap == 0
    for action in actions:
        with pytest.raises(FrozenInstanceError):
            action.extra = "raw input"
    assert all(type(action) not in typing.get_args(VillageControllerEvent)
               for action in actions)


@pytest.mark.parametrize("target", [-1, True, False, 1.0, "1", None])
def test_lod_unlock_action_validates_exact_id_and_cap(target):
    with pytest.raises(ValueError):
        ApplyLodUnlockAction(WorldObjectId("goblin", "location/well"), target)
    with pytest.raises(ValueError):
        ApplyLodUnlockAction("goblin:location/well", 1)


@pytest.mark.parametrize("raw", ["", "   ", "\r\n"])
def test_empty_input_resolves_to_none(raw):
    assert parse_raw_input(raw) is None


def test_menu_numbers_are_ui_indices_not_game_keys():
    assert parse_raw_input(" 1\n") == SelectMenuIndex(1)
    assert parse_raw_input("2") == SelectMenuIndex(2)
    assert parse_raw_input("01") == SelectMenuIndex(1)
    assert parse_raw_input("0") is None
    assert parse_raw_input("+1") == DirectCommand("+1")
    assert parse_raw_input("-1") == DirectCommand("-1")
    assert not hasattr(SelectMenuIndex(2), "key")


def test_menu_index_resolver_preserves_commands_and_bounds():
    commands = ["go north", "look", "depart"]
    before = copy.deepcopy(commands)
    assert resolve_menu_index(SelectMenuIndex(1), commands) == "go north"
    assert resolve_menu_index(SelectMenuIndex(3), commands) == "depart"
    assert resolve_menu_index(SelectMenuIndex(4), commands) is None
    assert commands == before


def test_shortcuts_preserve_uppercase_only_semantics():
    assert parse_raw_input("S") == MetaRequest("status")
    assert parse_raw_input("H") == MetaRequest("help")
    assert parse_raw_input("Q") == MetaRequest("quit")
    assert parse_raw_input("s") == DirectCommand("s")
    assert parse_raw_input("h") == DirectCommand("h")
    assert parse_raw_input("q") == DirectCommand("q")
    assert resolve_direction("s") == "south"


@pytest.mark.parametrize("raw, expected", [
    ("status", MetaRequest("status")),
    ("HELP", MetaRequest("help")),
    ("Quit", MetaRequest("quit")),
    ("save camp", MetaRequest("save", "camp")),
    ("LOAD My Save", MetaRequest("load", "My Save")),
    ("save", MetaRequest("save")),
    ("load   ", MetaRequest("load")),
])
def test_direct_meta_commands_are_classified_without_io(raw, expected):
    assert resolve_meta_request(raw) == expected
    assert parse_raw_input(raw) == expected
    assert not isinstance(parse_raw_input(raw), DirectCommand)


def test_meta_model_normalizes_arguments_and_rejects_irrelevant_arguments():
    assert MetaRequest("save", "  slot one  ").argument == "slot one"
    assert MetaRequest("load", " ").argument is None
    with pytest.raises(ValueError):
        MetaRequest("status", "extra")
    assert resolve_meta_request("status extra") is None


@pytest.mark.parametrize("raw, normalized", [
    ("attack", "attack"),
    (" MAGIC ", "magic"),
    ("north", "north"),
    ("GO NORTH", "go north"),
    ("unknown Command", "unknown command"),
])
def test_direct_commands_are_trimmed_and_lowercased(raw, normalized):
    token = parse_raw_input(raw)
    assert token == DirectCommand(normalized)


@pytest.mark.parametrize("direction, aliases", [
    ("north", ("north", "n", "北", "up")),
    ("east", ("east", "e", "東", "right")),
    ("south", ("south", "s", "南", "down")),
    ("west", ("west", "w", "西", "left")),
])
def test_all_existing_direction_aliases_and_prefixes(direction, aliases):
    for alias in aliases:
        assert resolve_direction(alias) == direction
        if alias.isascii():
            assert resolve_direction(alias.upper()) == direction
        for prefix in ("go", "move", "g", "walk"):
            assert resolve_direction(f"{prefix} {alias}") == direction
    assert resolve_direction(aliases[0]) == resolve_direction(aliases[0])


def test_direction_resolver_rejects_unknown_without_state_changes():
    assert resolve_direction("") is None
    assert resolve_direction("go") is None
    assert resolve_direction("go nowhere") is None
    assert resolve_direction("jump north") is None


@pytest.mark.parametrize("command", ["attack", "magic", "herb", "flee"])
def test_combat_commands_are_case_insensitive_and_allowed_is_read_only(command):
    allowed = ["attack", "flee"]
    before = list(allowed)
    assert resolve_combat_command(command.upper()) == command
    expected = command if command in allowed else None
    assert resolve_combat_command(command, allowed=allowed) == expected
    assert allowed == before


def test_combat_resolver_does_not_infer_resource_availability():
    assert resolve_combat_command("magic") == "magic"
    assert resolve_combat_command("herb") == "herb"
    assert resolve_combat_command("defend") is None
    assert resolve_combat_command("magic", allowed=("attack", "flee")) is None


def test_resolvers_do_not_change_game_state_rng_or_log():
    state = GameState(7, scenario=load_scenario("goblin"))
    before_snapshot = copy.deepcopy(state.snapshot())
    before_log = copy.deepcopy(state.log)
    before_rng = state.rng.state()
    assert parse_raw_input("2") == SelectMenuIndex(2)
    assert resolve_menu_index(SelectMenuIndex(1), ("attack",)) == "attack"
    assert resolve_direction("go north") == "north"
    assert resolve_combat_command("attack") == "attack"
    assert state.snapshot() == before_snapshot
    assert state.log == before_log
    assert state.rng.state() == before_rng


def test_input_module_has_no_ui_presentation_record_or_replay_dependency():
    import trpg_core.input_actions as input_actions

    source = input_actions.__loader__.get_source(input_actions.__name__)
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert all(not name.startswith("trpg_core") for name in imports)
    assert all(not name.startswith(".") for name in imports)
    assert "explore:" not in source and "choice:" not in source and "combat:" not in source
# Canonical village boundary -------------------------------------------------

def test_canonical_village_actions_are_frozen_and_resolved():
    object_id = WorldObjectId("goblin", "location/well")
    actions = (
        MoveToLocationAction(object_id), ExploreAction("well"), DepartAction(),
        SetFocusAction(object_id), ClearFocusAction(),
    )
    for action in actions:
        with pytest.raises(FrozenInstanceError):
            action.extra = "physical-input"
    assert actions[0].destination_object_id == object_id
    assert actions[1].key == "well"
    assert actions[3].object_id == object_id


def test_focus_navigation_cycles_and_rejects_invalid_context():
    candidates = tuple(WorldObjectId("goblin", f"location/{x}") for x in "abc")
    original = candidates
    assert resolve_focus_command("focus next", focused_object_id=None,
                                 focusable_object_ids=candidates) == SetFocusAction(candidates[0])
    assert resolve_focus_command("focus prev", focused_object_id=None,
                                 focusable_object_ids=candidates) == SetFocusAction(candidates[-1])
    assert resolve_focus_command("focus next", focused_object_id=candidates[-1],
                                 focusable_object_ids=candidates) == SetFocusAction(candidates[0])
    assert resolve_focus_command("focus prev", focused_object_id=candidates[0],
                                 focusable_object_ids=candidates) == SetFocusAction(candidates[-1])
    assert resolve_focus_command("focus clear", focused_object_id=candidates[0],
                                 focusable_object_ids=candidates) == ClearFocusAction()
    assert resolve_focus_command("look", focused_object_id=None,
                                 focusable_object_ids=candidates) is None
    assert candidates == original
    for command, focused, available in (
        ("focus next", None, ()),
        ("focus next", WorldObjectId("goblin", "location/x"), candidates),
        ("focus next", None, (candidates[0], candidates[0])),
        ("focus foo", None, candidates),
    ):
        with pytest.raises(ValueError):
            resolve_focus_command(command, focused_object_id=focused,
                                  focusable_object_ids=available)


def test_move_resolver_returns_destination_without_mutating_context():
    destination = WorldObjectId("goblin", "location/well")
    moves = (("north", destination),)
    assert resolve_move_action("north", move_destinations=moves) == MoveToLocationAction(destination)
    assert moves == (("north", destination),)
    assert resolve_move_action("look", move_destinations=moves) is None
    with pytest.raises(ValueError):
        resolve_move_action("south", move_destinations=moves)
