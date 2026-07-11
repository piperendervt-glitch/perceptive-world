"""固定画面TUIの描画・フォールバック・決定性境界テスト。"""

from __future__ import annotations

import builtins
import copy
import io
import os

import pytest

from trpg_core import record, session
from trpg_core.combat import run_combat
from trpg_core.map import build_map
from trpg_core.map_view import render_map
from trpg_core.presentation import (
    ActionView,
    EnemyView,
    PlayerView,
    PreparationView,
    PresentationContext,
    RenderSnapshot,
    WorldObjectView,
    build_map_view,
    build_render_snapshot,
)
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
    render_local_cross_map,
    screen_model_from_snapshot,
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
    assert "注目: なし" in screen
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


def test_message_buffer_messages_is_an_immutable_copy():
    messages = MessageBuffer()
    messages.add("最初")
    copied = messages.messages()
    messages.add("次")
    assert copied == ("最初",)
    assert messages.messages() == ("最初", "次")


def test_snapshot_adapter_is_pure_deterministic_and_formats_numbers(monkeypatch):
    snapshot = RenderSnapshot(
        scenario_id="beasts", scene_id="battle", scene_kind="combat",
        scene_title="獣道", scene_text="", turn=3, objective="獣を退ける",
        player=PlayerView(12, 20, 4, 10, "薬草", 1, 2),
        actions=(ActionView("attack", "combat", "攻撃"),
                 ActionView("flee", "combat", "逃げる")),
        enemies=(EnemyView("wolf", "狼", 7, True, True),
                 EnemyView("boar", "猪", 9, True, False)),
        recent_messages=("狼の攻撃をかわした。",),
    )
    before = copy.deepcopy(snapshot)
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("PERCEPTIVE_NO_ANSI", "1")
    first = screen_model_from_snapshot(snapshot)
    second = screen_model_from_snapshot(snapshot)
    assert first == second
    assert snapshot == before
    assert first.status == "HP 12/20  MP 4/10  薬草 1（持込予定 2）  ターン 3"
    assert first.situation == "狼 HP7 / 猪 HP9"
    assert first.scene == "自動対象: 狼"
    assert [item[1] for item in first.menu] == ["attack", "flee"]
    assert first.focus == "なし"


def test_snapshot_adapter_resolves_focused_label_not_tuple_position():
    snapshot = RenderSnapshot(
        scenario_id="goblin", scene_id="well", scene_kind="village",
        scene_title="古井戸", scene_text="", turn=0, objective="調べる",
        player=PlayerView(20, 20, 10, 10, "薬草", 0),
        world_objects=(
            WorldObjectView("goblin:object/well-mark", "mural", "井戸の印"),
            WorldObjectView("goblin:location/well", "location", "古井戸"),
        ),
        focused_object_id="goblin:location/well",
    )
    model = screen_model_from_snapshot(snapshot)
    assert model.focus == "古井戸"
    screen = render_screen(model, 80, 24)
    assert "注目: 古井戸" in screen
    assert "goblin:location/well" not in screen
    assert "注目: 井戸の印" not in screen


def test_snapshot_adapter_rejects_missing_focused_world_object():
    snapshot = RenderSnapshot(
        scenario_id="goblin", scene_id="well", scene_kind="village",
        scene_title="古井戸", scene_text="", turn=0, objective="調べる",
        player=PlayerView(20, 20, 10, 10, "薬草", 0),
        focused_object_id="goblin:location/well",
    )
    with pytest.raises(ValueError):
        screen_model_from_snapshot(snapshot)


def test_village_snapshot_adapter_uses_structured_map_and_preparation():
    state = GameState(7, scenario=load_scenario("ruins"))
    game_map = build_map(state.scenario, state.location)
    snapshot = build_render_snapshot(
        state,
        PresentationContext(
            scene_kind="village", scene_title=game_map.here().name,
            objective="支度をあと 1 つ整える", recovery_item_name="傷薬",
            pending_recovery_count=2,
            preparation=PreparationView(("one",), 1, 2, 2, False),
            map=build_map_view(game_map),
            actions=(ActionView("look", "village", "周囲を見る"),),
            recent_messages=("支度を始めた。",),
        ),
    )
    model = screen_model_from_snapshot(snapshot)
    assert model.place == game_map.here().name
    assert model.situation == "支度 1/2"
    assert game_map.here().name in model.scene
    assert all(game_map.dest_name(direction) in model.scene for direction in game_map.exits())
    assert model.objective == "支度をあと 1 つ整える"
    assert model.recent == ["支度を始めた。"]


@pytest.mark.parametrize("scenario_id", ["goblin", "ruins", "beasts"])
def test_map_view_reproduces_baseline_cross_map_at_every_location(scenario_id):
    scenario = load_scenario(scenario_id)
    assert all(
        set(location.get("exits", ())) <= {"north", "east", "south", "west"}
        for location in scenario.map_locations.values()
    )
    for location_id in scenario.map_locations:
        game_map = build_map(scenario, location_id)
        view = build_map_view(game_map)
        before = copy.deepcopy(view)
        first = render_local_cross_map(view)
        assert first == render_map(game_map)
        assert render_local_cross_map(view) == first
        assert view == before


def test_cross_map_places_all_four_exits_around_emphasized_center():
    scenario = load_scenario("goblin")
    game_map = build_map(scenario, "plaza")
    scene = render_local_cross_map(build_map_view(game_map))
    lines = scene.splitlines()
    center_index = next(i for i, line in enumerate(lines) if ">村の広場<" in line)
    center_line = lines[center_index]
    assert "[古井戸]" in "\n".join(lines[:center_index])
    assert "[古い祠]" in "\n".join(lines[center_index + 1:])
    assert center_line.index("[村長の家]") < center_line.index(">村の広場<")
    assert center_line.index(">村の広場<") < center_line.index("[薬草小屋]")
    for label in ("古井戸", "古い祠", "村長の家", "薬草小屋"):
        assert scene.count(f"[{label}]") == 1
    assert "北 →" not in scene and "東 →" not in scene


@pytest.mark.parametrize(
    ("scenario_id", "location_id", "destination", "arrow"),
    [("goblin", "lookout", "古井戸", "↓南"),
     ("ruins", "apoth", "崩れた石棚", "↓南"),
     ("beasts", "balmhut", "老猟師の小屋", "↓南")],
)
def test_cross_map_endpoint_shows_only_existing_exit(
        scenario_id, location_id, destination, arrow):
    scenario = load_scenario(scenario_id)
    scene = render_local_cross_map(build_map_view(build_map(scenario, location_id)))
    assert f">{scenario.map_locations[location_id]['name']}<" in scene
    assert f"[{destination}]" in scene
    assert arrow in scene
    assert "↑北" not in scene and " ← " not in scene and " → " not in scene


@pytest.mark.parametrize("scenario_id", ["goblin", "ruins", "beasts"])
def test_departure_location_keeps_return_exit_and_depart_command(scenario_id):
    state = GameState(7, scenario=load_scenario(scenario_id))
    controller = ConsoleController(state, os.devnull)
    exit_id = next(
        location_id for location_id, data in state.scenario.map_locations.items()
        if data.get("leads_to_adventure")
    )
    game_map = build_map(state.scenario, exit_id)
    scene = render_local_cross_map(build_map_view(game_map))
    destination = next(iter(game_map.here().exits.values()))
    assert f"[{game_map.locations[destination].name}]" in scene
    picked = state.scenario.village_order[:state.scenario.village_pick_count]
    assert controller._village_menu(game_map, state.scenario, picked)[0][1] == "depart"


def test_decision_adapter_preserves_action_order_labels_and_scene_once():
    state = GameState(7, scenario=load_scenario("goblin"))
    node = state.scenario.node(state.node)
    text = state.scenario.node_text(node.id)
    actions = tuple(ActionView(str(i), "decision", choice.label)
                    for i, choice in enumerate(node.choices, 1))
    snapshot = build_render_snapshot(
        state,
        PresentationContext(
            scene_kind="decision", scene_id=node.id, scene_title=node.title,
            scene_text=text, objective="次に取る行動を一つ選ぶ", actions=actions,
        ),
    )
    model = screen_model_from_snapshot(snapshot)
    assert model.scene == text
    assert model.scene.count(text) == 1
    assert [(label, command) for label, command, _detail in model.menu] == [
        (action.label, action.canonical_command) for action in actions
    ]


def test_normal_tui_path_builds_render_snapshot_without_side_effects(monkeypatch):
    import trpg_core.presentation as presentation

    state, controller = _controller()
    controller.tui = TerminalUI(stream=FakeTTY(), size_getter=_size(), environ={})
    game_map = build_map(state.scenario, state.location)
    menu = controller._village_menu(game_map, state.scenario, [])
    before = _fingerprint(state)
    current = game_map.current
    seen = []
    original = presentation.build_render_snapshot

    def spy(state_arg, context, *, active_game_map=None):
        result = original(state_arg, context, active_game_map=active_game_map)
        seen.append(result)
        return result

    monkeypatch.setattr(presentation, "build_render_snapshot", spy)
    controller._show_village_menu(game_map, state.scenario, [], menu)
    assert len(seen) == 1
    assert isinstance(seen[0], RenderSnapshot)
    assert _fingerprint(state) == before
    assert game_map.current == current


def test_menu_path_does_not_require_snapshot_adapter(monkeypatch, capsys):
    import trpg_core.tui as tui_module

    state, controller = _controller("menu")
    game_map = build_map(state.scenario, state.location)
    menu = controller._village_menu(game_map, state.scenario, [])
    monkeypatch.setattr(
        tui_module, "screen_model_from_snapshot",
        lambda _snapshot: (_ for _ in ()).throw(AssertionError("menu must not use TUI adapter")),
    )
    controller._show_village_menu(game_map, state.scenario, [], menu)
    output = capsys.readouterr().out
    assert "目的:" in output
    assert [item[1] for item in menu] == [
        item[1] for item in controller._village_menu(game_map, state.scenario, [])
    ]


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


def test_non_tty_fallback_uses_same_session_input_resolver(monkeypatch):
    state, controller = _controller("tui")
    stream = io.StringIO()
    controller.tui = TerminalUI(stream=stream, size_getter=_size(), environ={})
    node = state.scenario.node(state.scenario.start_node)
    calls = []
    original = session.parse_raw_input
    monkeypatch.setattr(session, "parse_raw_input",
                        lambda raw: calls.append(raw) or original(raw))
    monkeypatch.setattr(builtins, "input", lambda _prompt: "01")
    assert controller.choice(node.id, [c.key for c in node.choices]) == node.choices[0].key
    assert calls == ["01"]
    assert "menu表示へ切り替えます" in stream.getvalue()
