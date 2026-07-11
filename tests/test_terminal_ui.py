"""固定画面TUIの描画・フォールバック・決定性境界テスト。"""

from __future__ import annotations

import builtins
import copy
import io
import os

from trpg_core import record, session
from trpg_core.combat import run_combat
from trpg_core.map import build_map
from trpg_core.record import RecordingController
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import ConsoleController, GameState
from trpg_core.tui import (
    CLEAR_SCREEN,
    MessageBuffer,
    ScreenModel,
    TerminalUI,
    display_width,
    render_screen,
    wrap_display,
)


class FakeTTY(io.StringIO):
    def isatty(self):
        return True


def _size(columns=80, lines=24):
    return lambda: os.terminal_size((columns, lines))


def _controller(ui="menu"):
    state = GameState(7, scenario=load_scenario("goblin"))
    controller = ConsoleController(state, os.devnull, ui_mode=ui)
    return state, controller


def _fingerprint(state):
    return {"snapshot": copy.deepcopy(state.snapshot()), "log": copy.deepcopy(state.log)}


def _model():
    return ScreenModel(
        place="村の広場", situation="支度 0/3",
        status="HP 20/20  MP 10/10  薬草 0", objective="支度をあと3つ整える",
        scene="    [古井戸]\n       ↑北\n[村長]←>広場<→[薬草]",
        recent=["村へ戻ってきた。", "支度を始める。"],
        menu=[("北へ → 古井戸", "go north", "移動"),
              ("周囲を見る", "look", "地図")],
    )


def test_display_width_and_wrap_support_japanese_and_combining_marks():
    assert display_width("abc") == 3
    assert display_width("日本") == 4
    assert display_width("e\u0301") == 1
    assert all(display_width(line) <= 6 for line in wrap_display("日本語abc日本", 6))


def test_wrap_keeps_short_numeric_tokens_and_avoids_leading_punctuation():
    samples = ["HP 19", "MP 8", "目標8", "2D6[3,4]", "2D6[3,4]=7", "支度 2/3", "残 HP 12"]
    text = "攻撃結果 " + " ".join(samples) + "。次へ。"
    lines = wrap_display(text, 18)
    joined = "\n".join(lines)
    for token in samples:
        assert token in joined
        assert "\n" not in token
    assert all(display_width(line) <= 18 for line in lines)
    assert all(not line.startswith(tuple("、。）」』】〕〉》！？：／")) for line in lines)


def test_wrap_splits_only_a_token_that_exceeds_width():
    token = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    lines = wrap_display(token, 8)
    assert "".join(lines) == token
    assert all(display_width(line) <= 8 for line in lines)


def test_render_screen_stays_within_terminal_bounds():
    screen = render_screen(_model(), 60, 20)
    lines = screen.splitlines()
    assert len(lines) <= 20
    assert all(display_width(line) <= 60 for line in lines)
    assert "村の広場" in screen
    assert "HP 20/20" in screen
    assert "目的:" in screen
    assert "最近:" in screen
    assert "1) 北へ" in screen


def test_terminal_ui_draws_ansi_only_for_supported_tty():
    stream = FakeTTY()
    tui = TerminalUI(stream=stream, size_getter=_size(), environ={})
    assert tui.draw(_model())
    assert stream.getvalue().startswith(CLEAR_SCREEN)


def test_non_tty_small_terminal_and_environment_fallback_once():
    non_tty = io.StringIO()
    tui = TerminalUI(stream=non_tty, size_getter=_size(), environ={})
    assert not tui.draw(_model())
    assert not tui.draw(_model())
    assert CLEAR_SCREEN not in non_tty.getvalue()
    assert non_tty.getvalue().count("menu表示へ切り替えます") == 1

    small = TerminalUI(stream=FakeTTY(), size_getter=_size(59, 19), environ={})
    assert not small.can_render()
    disabled = TerminalUI(stream=FakeTTY(), size_getter=_size(),
                          environ={"PERCEPTIVE_NO_ANSI": "1"})
    assert not disabled.can_render()


def test_message_buffer_wraps_keeps_latest_and_is_not_in_snapshot():
    state, _controller_obj = _controller()
    before = copy.deepcopy(state.snapshot())
    messages = MessageBuffer(max_messages=2)
    messages.add("最初")
    messages.add("二番目の長いメッセージ")
    messages.add("最後")
    assert messages.recent_lines(6, 2)[-1] == "最後"
    assert state.snapshot() == before
    assert "messages" not in state.snapshot()


def test_message_buffer_drops_whole_old_messages_and_marks_truncated_latest():
    messages = MessageBuffer()
    messages.add("古い文章の先頭。古い文章の続き。")
    messages.add("新しい短文。")
    assert messages.recent_lines(20, 1) == ["新しい短文。"]

    long_latest = MessageBuffer()
    long_latest.add("これは非常に長い最新メッセージで、領域の高さを超えて続いていく。")
    lines = long_latest.recent_lines(10, 2)
    assert len(lines) == 2
    assert lines[0].startswith("…")
    assert not lines[0].startswith(("。", "、", "／"))


def test_tui_redraw_does_not_change_state_rng_or_log():
    state, controller = _controller()
    controller.tui = TerminalUI(stream=FakeTTY(), size_getter=_size(), environ={})
    sc = state.scenario
    gm = build_map(sc, sc.map_start)
    menu = controller._village_menu(gm, sc, [])
    before = _fingerprint(state)
    controller._show_village_menu(gm, sc, [], menu)
    assert _fingerprint(state) == before


def test_village_tui_shows_pending_scenario_item_without_applying_it():
    state = GameState(7, scenario=load_scenario("thief"))
    controller = ConsoleController(state, os.devnull)
    stream = FakeTTY()
    controller.tui = TerminalUI(stream=stream, size_getter=_size(), environ={})
    sc = state.scenario
    gm = build_map(sc, sc.map_start)
    picked = ["poultice"]
    before = _fingerprint(state)
    controller._show_village_menu(gm, sc, picked, controller._village_menu(gm, sc, picked))
    out = stream.getvalue()
    assert "傷薬 0（持込予定 2）" in out
    assert state.herbs == 0
    assert _fingerprint(state) == before


def test_choice_scene_is_not_duplicated_in_recent_messages(monkeypatch):
    state, controller = _controller()
    controller.tui = TerminalUI(stream=FakeTTY(), size_getter=_size(), environ={})
    node = state.scenario.node(state.scenario.start_node)
    text = state.scenario.node_text(node.id)
    monkeypatch.setattr(builtins, "input", lambda _prompt: "1")
    controller.choice(node.id, [c.key for c in node.choices])
    assert text not in list(controller.tui.messages._messages)


def test_tui_help_enter_is_not_recorded(monkeypatch):
    state, controller = _controller()
    controller.tui = TerminalUI(stream=FakeTTY(), size_getter=_size(), environ={})
    node = next(n for n in state.scenario.nodes.values() if n.kind == "combat")
    state.node = node.id
    enemies = state.scenario.make_group(node.encounter)
    rec = RecordingController(controller, state.scenario)
    answers = iter(["H", "", "1"])
    monkeypatch.setattr(builtins, "input", lambda _prompt: next(answers))
    before = _fingerprint(state)
    assert rec.combat_command(state, enemies) == "attack"
    assert rec.inputs == ["combat:attack"]
    assert _fingerprint(state) == before


def test_menu_and_tui_map_same_number_to_same_command():
    state_menu, menu_controller = _controller("menu")
    state_tui, tui_controller = _controller("menu")
    gm_menu = build_map(state_menu.scenario, state_menu.location)
    gm_tui = build_map(state_tui.scenario, state_tui.location)
    menu_a = menu_controller._village_menu(gm_menu, state_menu.scenario, [])
    menu_b = tui_controller._village_menu(gm_tui, state_tui.scenario, [])
    assert menu_a == menu_b
    assert menu_controller._menu_command("1", menu_a) == tui_controller._menu_command("1", menu_b)


def test_menu_and_tui_same_actions_produce_identical_combat(monkeypatch):
    state_menu, menu_controller = _controller("menu")
    state_tui, tui_controller = _controller("menu")
    tui_controller.tui = TerminalUI(stream=FakeTTY(), size_getter=_size(), environ={})
    node = next(n for n in state_menu.scenario.nodes.values() if n.kind == "combat")
    state_menu.node = node.id
    state_tui.node = node.id
    monkeypatch.setattr(builtins, "input", lambda _prompt: "1")
    result_menu = run_combat(state_menu, node.id, menu_controller)
    result_tui = run_combat(state_tui, node.id, tui_controller)
    assert result_menu == result_tui
    assert state_menu.log == state_tui.log
    assert state_menu.snapshot() == state_tui.snapshot()


def test_session_cli_defaults_to_menu_and_accepts_tui(monkeypatch):
    calls = []
    monkeypatch.setattr(session, "play_interactive",
                        lambda seed, scenario_id, ui_mode: calls.append((seed, scenario_id, ui_mode)))
    assert session.main(["--scenario", "envoy", "--seed", "0"]) == 0
    assert session.main(["--scenario", "envoy", "--seed", "0", "--ui", "tui"]) == 0
    assert calls == [(0, "envoy", "menu"), (0, "envoy", "tui")]


def test_record_cli_passes_ui_without_changing_fixture_format(monkeypatch):
    calls = []
    fixture = {"scenario": "envoy", "seed": 0, "inputs": [], "expected_log": []}
    monkeypatch.setattr(record, "_record_interactive",
                        lambda scenario_id, seed, ui_mode: calls.append(ui_mode) or fixture)
    monkeypatch.setattr(record, "save_fixture", lambda data, path: path)
    out = "trpg_core/logs/test-terminal-ui.json"
    assert record.main(["--scenario", "envoy", "--seed", "0", "--play",
                        "--ui", "tui", "--out", out]) == 0
    assert calls == ["tui"]
    assert set(fixture) == {"scenario", "seed", "inputs", "expected_log"}
