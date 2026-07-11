"""中立表示モデルのimmutable性・決定性・無副作用テスト。"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from trpg_core.map import build_map
from trpg_core.presentation import (
    ActionView,
    AttributeView,
    EnemyView,
    MapExitView,
    MapView,
    PlayerView,
    PreparationView,
    PresentationContext,
    RenderSnapshot,
    build_enemy_views,
    build_map_view,
    build_render_snapshot,
)
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import GameState


def _state(scenario_id="goblin"):
    return GameState(7, scenario=load_scenario(scenario_id))


def test_models_are_frozen_and_collections_are_copied_to_tuples():
    actions = [ActionView("attack", "combat", "攻撃")]
    messages = ["直近の出来事"]
    context = PresentationContext(actions=actions, recent_messages=messages)
    state = _state()
    snapshot = build_render_snapshot(state, context)

    actions.append(ActionView("flee", "combat", "逃走"))
    messages.append("後から追加")

    assert snapshot.actions == (ActionView("attack", "combat", "攻撃"),)
    assert snapshot.recent_messages == ("直近の出来事",)
    assert isinstance(snapshot.actions, tuple)
    assert isinstance(snapshot.player.attributes, tuple)
    assert isinstance(snapshot.player.buffs, tuple)
    for model in (AttributeView, PlayerView, ActionView, EnemyView, PreparationView,
                  MapExitView, MapView, PresentationContext, RenderSnapshot):
        assert model.__dataclass_params__.frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.turn = 99


def test_builder_is_deterministic_numeric_and_optional_context_is_empty(monkeypatch):
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setenv("PERCEPTIVE_NO_ANSI", "1")
    state = _state()
    first = build_render_snapshot(state)
    second = build_render_snapshot(state)

    assert first == second
    assert isinstance(first.turn, int)
    assert isinstance(first.player.hp, int)
    assert isinstance(first.player.mp, int)
    assert first.actions == ()
    assert first.enemies == ()
    assert first.preparation is None
    assert first.map is None
    assert first.recent_messages == ()
    assert first.ending is None
    assert "\x1b" not in repr(first)


def test_builder_does_not_change_game_state_log_or_rng(monkeypatch):
    state = _state()
    before_snapshot = copy.deepcopy(state.snapshot())
    before_log = copy.deepcopy(state.log)
    before_rng = state.rng.state()

    def forbidden_emit(**_fields):
        raise AssertionError("builder must not emit")

    monkeypatch.setattr(state, "emit", forbidden_emit)
    build_render_snapshot(state, PresentationContext(objective="進む"))

    assert state.snapshot() == before_snapshot
    assert state.log == before_log
    assert state.rng.state() == before_rng


def test_player_attributes_and_preparation_keep_structured_numbers():
    state = _state()
    preparation = PreparationView(
        selected_keys=["elder"], selected_count=1, required_count=3,
        pending_recovery_count=2, ready_to_depart=False,
    )
    snapshot = build_render_snapshot(
        state,
        PresentationContext(preparation=preparation, pending_recovery_count=2),
    )

    assert snapshot.player.hp == state.hp
    assert snapshot.player.mp == state.mp
    assert snapshot.player.pending_recovery_count == 2
    assert snapshot.preparation.selected_count == 1
    assert snapshot.preparation.required_count == 3
    assert snapshot.preparation.selected_keys == ("elder",)
    assert [(a.key, a.value, a.modifier) for a in snapshot.player.attributes] == [
        ("str", state.str, state.str - 8),
        ("mag", state.mag, state.mag - 8),
        ("vit", state.vit, state.vit - 8),
    ]


def test_enemy_views_copy_values_and_mark_only_first_alive_as_auto_target():
    enemies = load_scenario("goblin").make_group(["goblin", "goblin"])
    enemies[0].hp = 0
    views = build_enemy_views(enemies)
    old_hp = views[1].hp
    enemies[1].hp -= 1

    assert views[0].alive is False
    assert views[0].auto_target is False
    assert views[1].alive is True
    assert views[1].auto_target is True
    assert views[1].hp == old_hp
    assert all(not isinstance(view, type(enemies[0])) for view in views)


def test_map_view_copies_current_location_and_visible_exits_without_moving():
    scenario = load_scenario("goblin")
    game_map = build_map(scenario)
    before = game_map.current
    view = build_map_view(game_map)

    assert game_map.current == before
    assert view.current_location == before
    assert view.current_label == game_map.here().name
    assert isinstance(view.exits, tuple)
    assert {(e.direction, e.destination) for e in view.exits} == set(game_map.here().exits.items())


@pytest.mark.parametrize("scenario_id", ["goblin", "ruins"])
def test_builder_supports_multiple_existing_scenarios(scenario_id):
    state = _state(scenario_id)
    node = state.scenario.node(state.node)
    snapshot = build_render_snapshot(
        state,
        PresentationContext(
            scene_id=node.id,
            scene_kind=node.kind,
            scene_title=node.title,
            scene_text="".join(node.text),
            actions=[ActionView(c.key, "choice", c.label) for c in node.choices],
        ),
    )
    assert snapshot.scenario_id == scenario_id
    assert snapshot.scene_id == node.id
    assert all(action.canonical_command in {c.key for c in node.choices}
               for action in snapshot.actions)


def test_presentation_module_has_no_ui_or_terminal_dependency():
    import trpg_core.presentation as presentation

    source = presentation.__loader__.get_source(presentation.__name__)
    forbidden = (
        "trpg_core.tui", "TerminalUI", "ScreenModel", "ConsoleController",
        "RecordingController", "FixtureController", "isatty", "get_terminal_size",
        "CLEAR_SCREEN", "sys.stdout", "input(",
    )
    assert all(term not in source for term in forbidden)
