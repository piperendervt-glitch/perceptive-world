"""中立表示モデルのimmutable性・決定性・無副作用テスト。"""

from __future__ import annotations

import copy
import dataclasses

import pytest

from trpg_core.map import build_map
from trpg_core.presentation import (
    FocusedObjectLodView,
    VisibleWorldFactView,
    ActionView,
    AttributeView,
    EnemyView,
    MapExitView,
    MapView,
    PlayerView,
    PreparationView,
    PresentationContext,
    RenderSnapshot,
    WorldObjectView,
    build_enemy_views,
    build_map_view,
    build_render_snapshot,
)
from trpg_core.lod import ObjectAttentionState, ObjectLodState
from trpg_core.lod_actions import LodRuntimeState, ObjectLodProgress
from trpg_core.world import WorldFact, WorldObjectId
from trpg_core.presentation import focused_object_lod_view, visible_world_fact_view
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import GameState
from trpg_core.world import location_world_object_id


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
                  MapExitView, MapView, WorldObjectView, PresentationContext,
                  RenderSnapshot):
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
    assert first.world_objects == ()
    assert first.focused_object_id is None
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


def test_world_object_view_is_frozen_and_holds_only_primitives():
    view = WorldObjectView("goblin:location/well", "location", "古井戸")
    assert dataclasses.asdict(view) == {
        "object_id": "goblin:location/well", "kind": "location", "label": "古井戸",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.label = "変更"


def test_map_scene_exposes_only_current_world_object_without_auto_focus():
    state = _state()
    game_map = build_map(state.scenario, "well")
    focus_before = state.focus_state
    snapshot = build_render_snapshot(
        state,
        PresentationContext(scene_kind="village", scene_id="well"),
        active_game_map=game_map,
    )
    assert snapshot.world_objects == (
        WorldObjectView("goblin:location/well", "location", "古井戸"),
    )
    assert snapshot.focused_object_id is None
    assert state.focus_state is focus_before


def test_map_scene_exposes_serialized_focused_object_id_without_side_effects():
    state = _state()
    game_map = build_map(state.scenario, "well")
    object_id = location_world_object_id("goblin", "well")
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    before = (copy.deepcopy(state.snapshot()), state.rng.state(), copy.deepcopy(state.log),
              state.focus_state, game_map.current, dict(game_map.locations))
    snapshot = build_render_snapshot(
        state, PresentationContext(scene_kind="village", scene_id="well"),
        active_game_map=game_map,
    )
    assert snapshot.focused_object_id == "goblin:location/well"
    assert isinstance(snapshot.focused_object_id, str)
    assert snapshot.world_objects[0].label == "古井戸"
    after = (state.snapshot(), state.rng.state(), state.log, state.focus_state,
             game_map.current, game_map.locations)
    assert after == before


def test_non_map_scene_has_no_world_objects_and_dangling_focus_is_rejected():
    state = _state()
    snapshot = build_render_snapshot(state, PresentationContext(scene_kind="decision"))
    assert snapshot.world_objects == ()
    assert snapshot.focused_object_id is None

    object_id = location_world_object_id("goblin", "well")
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    before = (copy.deepcopy(state.snapshot()), state.rng.state(), copy.deepcopy(state.log),
              state.focus_state)
    with pytest.raises(ValueError):
        build_render_snapshot(state, PresentationContext(scene_kind="decision"))
    assert (state.snapshot(), state.rng.state(), state.log, state.focus_state) == before
def test_lod_presentation_views_are_strict_frozen_and_minimal():
    fact = VisibleWorldFactView("shape", "well_like", "井戸らしき形")
    view = FocusedObjectLodView(WorldObjectId("goblin", "location/well"), 0, (fact,))
    assert set(view.__dict__) == {
        "object_id", "current_lod", "visible_facts", "has_more_observable_detail",
    }
    assert view.has_more_observable_detail is False
    assert set(fact.__dict__) == {"key", "value", "label"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        fact.label = "changed"
    for bad in ("", " x", "x ", 1, None):
        with pytest.raises(ValueError):
            VisibleWorldFactView(bad, "v", "label")
    with pytest.raises(ValueError):
        FocusedObjectLodView(view.object_id, True, ())
    with pytest.raises(ValueError):
        FocusedObjectLodView(view.object_id, 0, [fact])


def test_exact_well_fact_label_mapping_rejects_fallbacks():
    well = WorldObjectId("goblin", "location/well")
    expected = (
        ("shape", "well_like", "井戸らしき形"), ("material", "stone", "石造り"),
        ("age", "old", "古い"), ("pulley", "recent", "新しい滑車"),
        ("rope", "worn", "擦り切れた縄"),
        ("mark", "faded_emblem", "消えかけた紋章"),
    )
    assert tuple(visible_world_fact_view(well, WorldFact(k, v)).label
                 for k, v, _ in expected) == tuple(label for _, _, label in expected)
    with pytest.raises(ValueError):
        visible_world_fact_view(well, WorldFact("shape", "wrong"))
    with pytest.raises(ValueError):
        visible_world_fact_view(WorldObjectId("other", "location/well"),
                                WorldFact("shape", "well_like"))


@pytest.mark.parametrize("attention, cap, lod, keys", [
    (0, 3, 0, ("shape",)),
    (1, 3, 1, ("shape", "material", "age")),
    (3, 3, 2, ("shape", "material", "age", "pulley", "rope")),
    (6, 3, 3, ("shape", "material", "age", "pulley", "rope", "mark")),
    (6, 1, 1, ("shape", "material", "age")),
])
def test_focused_lod_projection_exposes_only_current_visible_facts(attention, cap, lod, keys):
    well = WorldObjectId("goblin", "location/well")
    progress = ObjectLodProgress(well, ObjectAttentionState(attention), ObjectLodState(cap))
    runtime = LodRuntimeState((progress,))
    before = copy.deepcopy(runtime)
    view = focused_object_lod_view(focused_object_id=well, lod_runtime=runtime)
    assert view.current_lod == lod
    assert tuple(f.key for f in view.visible_facts) == keys
    assert runtime == before
    assert not any(name in view.__dict__ for name in ("hidden", "attention", "cap"))


def test_focused_lod_projection_is_opt_in_and_empty_runtime_is_read_only():
    well = WorldObjectId("goblin", "location/well")
    runtime = LodRuntimeState()
    assert focused_object_lod_view(focused_object_id=None, lod_runtime=runtime) is None
    assert focused_object_lod_view(focused_object_id=well, lod_runtime=None) is None
    assert focused_object_lod_view(
        focused_object_id=WorldObjectId("other", "location/well"), lod_runtime=runtime,
    ) is None
    view = focused_object_lod_view(focused_object_id=well, lod_runtime=runtime)
    assert view.current_lod == 0
    assert tuple(f.key for f in view.visible_facts) == ("shape",)
    assert runtime == LodRuntimeState()
def test_well_snapshot_exposes_neutral_spatial_view_without_mutation():
    import copy
    from trpg_core.map import build_map
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState
    from trpg_core.spatial import PlayerPosition

    state = GameState(7, scenario=load_scenario("goblin"))
    state.transition_location("well")
    game_map = build_map(state.scenario, "well")
    before = (copy.deepcopy(state.snapshot()), state.player_position, state.focus_state)
    snapshot = build_render_snapshot(state, active_game_map=game_map)
    scene = snapshot.spatial_scene
    assert (scene.width, scene.height) == (7, 5)
    assert scene.player_position.x == 3 and scene.player_position.y == 3
    assert len(scene.walkable_cells) == 17
    assert len(scene.objects) == 1 and scene.objects[0].label == "古井戸"
    assert [(item.position.x, item.position.y, item.label, item.transition_kind)
            for item in scene.exits] == [
        (3, 4, "村の広場", "move"), (3, 0, "物見櫓", "move"),
    ]
    assert scene.objects[0].focus_candidate is True
    assert (state.snapshot(), state.player_position, state.focus_state) == before


def test_plaza_snapshot_has_current_catalog_spatial_view():
    from trpg_core.map import build_map
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState
    state = GameState(7, scenario=load_scenario("goblin"))
    assert build_render_snapshot(
        state, active_game_map=build_map(state.scenario, state.location),
    ).spatial_scene is not None


def test_all_goblin_landmarks_have_distinct_safe_glyphs():
    from trpg_core.map import build_map
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState
    scenario = load_scenario("goblin")
    glyphs = {}
    for scene_id in scenario.map_locations:
        state = GameState(7, scenario=scenario)
        if scene_id != state.location:
            definition = state.spatial_definition_for_location(scene_id)
            source = definition.entry_spawns[0].source_scene_id.local_id.removeprefix(
                "location/",
            )
            state.transition_location(scene_id, source_location=source)
        scene = build_render_snapshot(
            state, active_game_map=build_map(scenario, scene_id),
        ).spatial_scene
        glyphs[scene_id] = scene.objects[0].glyph
        assert ":" not in scene.objects[0].glyph
    assert glyphs == {
        "plaza": "広", "well": "井", "lookout": "櫓",
        "herbhut": "薬", "shrine": "祠", "elderhouse": "長",
        "forest_gate": "門",
    }
