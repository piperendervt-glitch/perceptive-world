"""コンパクトなコンソールメニューの回帰テスト。"""

from __future__ import annotations

import builtins
import copy
import os

import pytest

from trpg_core.map import build_map
from trpg_core.record import RecordingController
from trpg_core.scenario_loader import load_scenario
from trpg_core import session
from trpg_core.input_actions import MovePlayerToPositionAction, MetaRequest, parse_raw_input
from trpg_core.session import (
    ConsoleController, GameState, _village_context, list_explore_and_pick,
)
from trpg_core.spatial import PlayerPosition


def _controller(seed=7, scenario_id="goblin"):
    state = GameState(seed, scenario=load_scenario(scenario_id))
    return state, ConsoleController(state, os.devnull)


def _fingerprint(state):
    return {"snapshot": copy.deepcopy(state.snapshot()), "log": copy.deepcopy(state.log)}


def _combat(state):
    node = next(n for n in state.scenario.nodes.values() if n.kind == "combat")
    state.node = node.id
    return node, state.scenario.make_group(node.encounter)


def test_village_menu_is_dynamic_contiguous_and_stably_ordered(capsys):
    state, controller = _controller()
    sc = state.scenario
    gm = build_map(sc, sc.map_start)
    menu = controller._village_menu(gm, sc, [])

    commands = [item[1] for item in menu]
    expected_moves = [f"go {d}" for d in ("north", "east", "south", "west")
                      if d in gm.exits()]
    prefix = ["do"] if gm.here().action else []
    assert commands == prefix + expected_moves + ["look"]

    controller._show_village_menu(gm, sc, [], menu)
    out = capsys.readouterr().out
    assert gm.here().name in out
    assert "目的:" in out
    assert [line.split(")", 1)[0] for line in out.splitlines() if ") " in line] == [
        str(i) for i in range(1, len(menu) + 1)
    ]
    assert "例:" not in out and "使用可能なコマンド:" not in out
    assert "[S] 状態  [H] ヘルプ  [Q] 終了" in out


def test_depart_only_appears_at_ready_exit():
    state, controller = _controller()
    sc = state.scenario
    exit_id = next(lid for lid, data in sc.map_locations.items()
                   if data.get("leads_to_adventure"))
    gm = build_map(sc, exit_id)
    assert "depart" not in [x[1] for x in controller._village_menu(gm, sc, [])]
    picked = sc.village_order[:sc.village_pick_count]
    assert [x[1] for x in controller._village_menu(gm, sc, picked)][0] == "depart"


def test_map_number_converts_to_existing_command_and_s_keeps_south():
    state, controller = _controller()
    sc = state.scenario
    gm = build_map(sc, sc.map_start)
    menu = controller._village_menu(gm, sc, [])
    south_index = next(i for i, item in enumerate(menu, 1) if item[1] == "go south")
    assert controller._menu_command(str(south_index), menu) == "go south"
    assert controller._meta_shortcut("S") == "status"
    assert controller._meta_shortcut("s") == "s"


def test_line_step_resolves_exact_destination_without_state_change(monkeypatch):
    state, controller = _controller()
    state.transition_location("well")
    game_map = build_map(state.scenario, "well")
    context = _village_context(state, game_map, [])
    answers = iter(["STEP EAST", "step east"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    action = controller.village_action(context, game_map=game_map, picked=())
    assert action == MovePlayerToPositionAction(PlayerPosition(4, 3))
    assert state.player_position == PlayerPosition(3, 3)


def test_help_distinguishes_go_and_step(capsys):
    _state, controller = _controller()
    controller._show_help([])
    out = capsys.readouterr().out
    assert "go <方角>" in out and "location間移動" in out
    assert "step north|east|south|west" in out and "1セル移動" in out


def test_combat_menu_filters_state_and_maps_number(capsys):
    state, controller = _controller()
    _node, enemies = _combat(state)
    state.mp = 0
    state.herbs = 0
    menu = controller._combat_menu(state, enemies)
    assert [x[1] for x in menu] == ["attack", "flee"]
    assert controller._menu_command("1", menu) == "attack"
    assert "自動" in menu[0][0] and enemies[0].name_ja in menu[0][0]

    controller._show_combat_menu(state, enemies, menu)
    out = capsys.readouterr().out
    assert "magic" not in out and "herb" not in out and "例:" not in out

    state.mp = state.mp_max
    state.herbs = 1
    assert [x[1] for x in controller._combat_menu(state, enemies)] == [
        "attack", "magic", "herb", "flee",
    ]


def test_help_has_details_legacy_commands_and_save_load(capsys):
    state, controller = _controller()
    _node, enemies = _combat(state)
    menu = controller._combat_menu(state, enemies)
    controller._show_help(menu, include_load=False)
    out = capsys.readouterr().out
    assert "数字または [コマンド]" in out
    assert "[attack]" in out
    assert "save <名前>" in out
    assert "load は戦闘外" in out
    assert "S / status" in out and "H / help" in out and "Q / quit" in out


def test_choice_help_invalid_and_short_status_do_not_change_state(monkeypatch, capsys):
    state, controller = _controller()
    node = state.scenario.node(state.scenario.start_node)
    before = _fingerprint(state)
    answers = iter(["H", "99", "S", "1"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    chosen = controller.choice(node.id, [c.key for c in node.choices])
    out = capsys.readouterr().out
    assert chosen == node.choices[0].key
    assert "── ヘルプ ──" in out
    assert "その選択は使用できません。" in out
    assert "H の内心" in out
    assert _fingerprint(state) == before


def test_combat_help_invalid_and_number_do_not_change_state(monkeypatch, capsys):
    state, controller = _controller()
    _node, enemies = _combat(state)
    before = _fingerprint(state)
    enemy_hp = [e.hp for e in enemies]
    answers = iter(["help", "99", "1"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    chosen = controller.combat_command(state, enemies)
    out = capsys.readouterr().out
    assert chosen == "attack"
    assert "その選択は使用できません。" in out
    assert [e.hp for e in enemies] == enemy_hp
    assert _fingerprint(state) == before


def test_recording_receives_normalized_combat_command(monkeypatch):
    state, controller = _controller()
    _node, enemies = _combat(state)
    rec = RecordingController(controller, state.scenario)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "1")
    assert rec.combat_command(state, enemies) == "attack"
    assert rec.inputs == ["combat:attack"]


@pytest.mark.parametrize("load_command", ["load slot", "LOAD slot", "Load slot"])
def test_combat_rejects_load_before_side_effects(
        load_command, monkeypatch, capsys):
    state, controller = _controller()
    _node, enemies = _combat(state)
    before = _fingerprint(state)
    enemy_state = [(enemy.hp, enemy.alive) for enemy in enemies]
    rec = RecordingController(controller, state.scenario)

    def unexpected_load(_name):
        pytest.fail("combat load must be rejected before _load()")

    monkeypatch.setattr(controller, "_load", unexpected_load)
    answers = iter([load_command, "attack"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert rec.combat_command(state, enemies) == "attack"
    assert "戦闘中のロードは非対応。安全な選択肢で load を。" in capsys.readouterr().out
    assert _fingerprint(state) == before
    assert [(enemy.hp, enemy.alive) for enemy in enemies] == enemy_state
    assert rec.inputs == ["combat:attack"]


def test_argumentless_combat_load_keeps_existing_invalid_input_behavior(
        monkeypatch, capsys):
    state, controller = _controller()
    _node, enemies = _combat(state)
    before = _fingerprint(state)
    answers = iter(["load", "attack"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))

    assert controller.combat_command(state, enemies) == "attack"
    out = capsys.readouterr().out
    assert "戦闘中のロードは非対応" not in out
    assert "その選択は使用できません。" in out
    assert _fingerprint(state) == before


@pytest.mark.parametrize(
    ("scenario_id", "destination", "forbidden"),
    [
        ("goblin", "森の道", None),
        ("thief", "裏木戸", "森"),
        ("beasts", "獣道の入口", None),
        ("ruins", "遺跡の口", "森"),
        ("envoy", "中州の会談", "森"),
    ],
)
def test_departure_wording_uses_scenario_destination(
        scenario_id, destination, forbidden, capsys):
    state, controller = _controller(scenario_id=scenario_id)
    sc = state.scenario
    exit_id = next(lid for lid, data in sc.map_locations.items()
                   if data.get("leads_to_adventure"))
    gm = build_map(sc, exit_id)
    picked = sc.village_order[:sc.village_pick_count]
    before = _fingerprint(state)
    menu = controller._village_menu(gm, sc, picked)
    controller._show_village_menu(gm, sc, picked, menu)
    out = capsys.readouterr().out
    assert destination in menu[0][0]
    assert destination in out
    if forbidden:
        assert forbidden not in menu[0][0]
        assert "村の出口" not in out
    assert _fingerprint(state) == before


@pytest.mark.parametrize("scenario_id", ["goblin", "thief", "beasts", "ruins", "envoy"])
def test_respawn_uses_scenario_defeat_text(scenario_id, capsys):
    state, controller = _controller(scenario_id=scenario_id)
    state.respawn_on_defeat = True
    controller.present_event({"type": "respawn", "hp": state.hp, "mp": state.mp})
    out = capsys.readouterr().out
    assert state.scenario.ending_text("defeat") in out


def test_internal_check_tag_gets_unique_scenario_label():
    _state, controller = _controller(scenario_id="thief")
    label = controller._scenario_check_label("crawl")
    assert "崩れ坑" in label and "vit" in label
    assert "crawl" not in label


@pytest.mark.parametrize("scenario_id", ["goblin", "thief", "beasts", "ruins", "envoy"])
def test_all_scenario_check_tags_have_safe_player_labels(scenario_id):
    state, controller = _controller(scenario_id=scenario_id)
    built_in = {"sneak", "vit_check"}
    for node in state.scenario.nodes.values():
        for choice in node.choices:
            check = choice.check or {}
            tag = check.get("tag")
            if not tag or tag in built_in:
                continue
            label = controller._scenario_check_label(tag)
            assert label != tag
            assert tag not in label
            assert "〔" in label or label == "判定"


def test_menu_number_wrapper_uses_new_index_semantics_without_changing_invalid_tokens():
    menu = [("first", "attack", ""), ("last", "flee", "")]
    assert ConsoleController._menu_command("01", menu) == "attack"
    assert ConsoleController._menu_command("2", menu) == "flee"
    assert ConsoleController._menu_command("0", menu) == "0"
    assert ConsoleController._menu_command("3", menu) == "3"
    assert ConsoleController._menu_command("+1", menu) == "+1"
    assert ConsoleController._menu_command("-1", menu) == "-1"


def test_decision_input_calls_raw_parser_and_returns_existing_choice_key(monkeypatch):
    state, controller = _controller()
    node = state.scenario.node(state.scenario.start_node)
    calls = []
    original = session.parse_raw_input

    def spy(raw):
        calls.append(raw)
        return original(raw)

    monkeypatch.setattr(session, "parse_raw_input", spy)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "01")
    assert controller.choice(node.id, [c.key for c in node.choices]) == node.choices[0].key
    assert calls == ["01"]


def test_list_preparation_uses_parser_but_returns_only_explore_keys(monkeypatch):
    state, controller = _controller()
    calls = []
    original = session.parse_raw_input
    answers = iter(["01", "01", "01"])
    monkeypatch.setattr(session, "parse_raw_input",
                        lambda raw: calls.append(raw) or original(raw))
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    picked = list_explore_and_pick(controller)
    assert picked == state.scenario.village_order[:state.scenario.village_pick_count]
    assert calls == ["01", "01", "01"]


def test_village_south_input_is_resolved_before_existing_move_handler(monkeypatch):
    state, controller = _controller()
    seen = []

    class StopWalk(Exception):
        pass

    def stop(_gm, _sc, _picked, direction):
        seen.append(direction)
        raise StopWalk

    monkeypatch.setattr(controller, "_try_move", stop)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "s")
    with pytest.raises(StopWalk):
        controller._walk_village(state.scenario)
    assert seen == ["south"]


def test_combat_input_uses_parser_and_allowed_resolver(monkeypatch):
    state, controller = _controller()
    _node, enemies = _combat(state)
    parse_calls = []
    combat_calls = []
    original_parse = session.parse_raw_input
    original_combat = session.resolve_combat_command
    monkeypatch.setattr(session, "parse_raw_input",
                        lambda raw: parse_calls.append(raw) or original_parse(raw))

    def combat_spy(text, *, allowed=None):
        combat_calls.append((text, tuple(allowed)))
        return original_combat(text, allowed=allowed)

    monkeypatch.setattr(session, "resolve_combat_command", combat_spy)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "ATTACK")
    assert controller.combat_command(state, enemies) == "attack"
    assert parse_calls == ["ATTACK"]
    assert combat_calls == [("attack", tuple(controller._combat_options(state)))]


def test_scene_specific_meta_case_compatibility_is_preserved():
    uppercase_status = parse_raw_input("STATUS")
    uppercase_help = parse_raw_input("HELP")
    assert isinstance(uppercase_status, MetaRequest)
    assert ConsoleController._legacy_meta_command(
        "STATUS", uppercase_status, casefold=False) is None
    assert ConsoleController._legacy_meta_command(
        "STATUS", uppercase_status, casefold=True) == "status"
    assert ConsoleController._legacy_meta_command(
        "HELP", uppercase_help, casefold=False) == "help"
