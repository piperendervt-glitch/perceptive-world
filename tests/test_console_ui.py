"""コンパクトなコンソールメニューの回帰テスト。"""

from __future__ import annotations

import builtins
import copy
import os

from trpg_core.map import build_map
from trpg_core.record import RecordingController
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import ConsoleController, GameState


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
