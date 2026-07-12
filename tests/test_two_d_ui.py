import sys

from trpg_core.input_actions import (
    ClearFocusAction, InspectFocusedObjectAction, MovePlayerToPositionAction,
    ObserveFocusedObjectAction, SetFocusAction,
)
from trpg_core.presentation import SceneSpatialView, SpatialCellView, SpatialObjectView
from trpg_core.spatial import PlayerPosition
from trpg_core.two_d import (
    HoverDwellController, TwoDClientAdapter, TwoDSessionModel, build_two_d_layout,
    make_available_action_callback, normalized_keyboard_code, pixel_rect_for_cell,
)
from trpg_core.world import WorldObjectId


def test_import_creates_no_tk_root_and_keyboard_reuses_adapter():
    assert "tkinter" not in sys.modules
    adapter = TwoDClientAdapter()
    assert normalized_keyboard_code("Up") == "ArrowUp"
    assert normalized_keyboard_code("w", "W") == "KeyW"
    assert adapter.movement_action(PlayerPosition(1, 2), "d", "d") == MovePlayerToPositionAction(PlayerPosition(2, 2))
    assert adapter.movement_action(None, "d", "d") is None


def test_client_actions_are_canonical_and_hover_render_have_no_action():
    object_id = WorldObjectId("goblin", "location/well")
    scene = SceneSpatialView(7, 5, (), (), None, (
        SpatialObjectView(object_id, "古井戸", SpatialCellView(3, 2), True, True),
    ))
    layout = build_two_d_layout(window_width=1000, window_height=700, scene_width=7, scene_height=5)
    rect = pixel_rect_for_cell(layout, SpatialCellView(3, 2))
    adapter = TwoDClientAdapter()
    assert adapter.click_action(scene, layout, rect.left, rect.top) == SetFocusAction(object_id)
    assert adapter.click_action(scene, layout, 0, 0) is None
    assert adapter.observe_action() == ObserveFocusedObjectAction()
    assert adapter.inspect_action() == InspectFocusedObjectAction()
    assert adapter.clear_focus_action() == ClearFocusAction()


def test_session_model_connects_actions_keys_click_and_redraw_to_shared_engine():
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState

    state = GameState(7, scenario=load_scenario("goblin"))
    model = TwoDSessionModel(state)
    assert model.snapshot.scene_title == "村の広場"
    assert model.snapshot.objective == "支度をあと3つ整える"
    assert [label for label, _action in model.available_actions] == [
        "北へ → 古井戸", "東へ → 薬草小屋", "南へ → 古い祠",
        "西へ → 村長の家", "周囲を見る",
    ]
    assert all(label for label, _action in model.available_actions)
    well_action = next(action for label, action in model.available_actions if "古井戸" in label)
    before_builds = model.snapshot_builds
    assert model.dispatch(well_action)
    assert state.location == "well" and state.player_position == PlayerPosition(1, 2)
    assert model.snapshot_builds == before_builds + 1
    assert [label for label, _action in model.available_actions] != [
        "北へ → 古井戸", "東へ → 薬草小屋", "南へ → 古い祠",
        "西へ → 村長の家", "周囲を見る",
    ]
    assert model.handle_key("d", "d") == MovePlayerToPositionAction(PlayerPosition(2, 2))
    assert state.player_position == PlayerPosition(2, 2)
    model.handle_key("d", "d")
    assert state.player_position == PlayerPosition(2, 2) and model.feedback
    model.handle_key("w", "w")
    assert state.player_position == PlayerPosition(2, 1)

    scene = model.snapshot.spatial_scene
    layout = build_two_d_layout(window_width=1000, window_height=700,
                                scene_width=scene.width, scene_height=scene.height)
    rect = pixel_rect_for_cell(layout, scene.objects[0].position)
    assert isinstance(model.handle_click(layout, rect.left+1, rect.top+1), SetFocusAction)
    assert model.snapshot.focused_object_lod.current_lod == 0
    model.handle_key("o", "o")
    assert model.snapshot.focused_object_lod.current_lod == 1
    model.handle_key("i", "i")
    assert model.snapshot.focused_object_lod.current_lod == 2
    assert model.handle_key("q", "q") == "quit" and model.closed


def test_action_callbacks_capture_distinct_indices_and_refocus():
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState
    model = TwoDSessionModel(GameState(7, scenario=load_scenario("goblin")))
    called = []
    callbacks = [
        make_available_action_callback(model, index,
                                       lambda: called.append("redraw"),
                                       lambda: called.append("focus"))
        for index in range(len(model.available_actions))
    ]
    callbacks[4]()
    assert model.state.location == "plaza"
    assert model.feedback == "周囲を見渡した"
    callbacks[0]()
    assert model.state.location == "well"
    assert called == ["redraw", "focus", "redraw", "focus"]


def test_no_position_and_rejected_actions_are_nonfatal_and_render_is_pure():
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState
    model = TwoDSessionModel(GameState(7, scenario=load_scenario("goblin")))
    builds = model.snapshot_builds
    assert model.handle_key("w", "w") is None
    assert "position" in model.feedback.lower()
    assert model.redraw_only() is model.snapshot
    assert model.snapshot_builds == builds
    assert model.handle_key("o", "o") == ObserveFocusedObjectAction()
    assert model.feedback and not model.closed


class _Scheduler:
    def __init__(self):
        self.callbacks = {}; self.cancelled = set(); self.next_id = 0
    def schedule(self, delay, callback):
        self.next_id += 1; self.callbacks[self.next_id] = (delay, callback); return self.next_id
    def cancel(self, timer_id): self.cancelled.add(timer_id)
    def fire(self, timer_id):
        if timer_id not in self.cancelled: self.callbacks[timer_id][1]()


def _dwell_setup():
    from trpg_core.scenario_loader import load_scenario
    from trpg_core.session import GameState
    state = GameState(7, scenario=load_scenario("goblin")); state.transition_location("well")
    model = TwoDSessionModel(state); scheduler = _Scheduler(); actions = []
    def dispatch(action):
        actions.append(action); return model.dispatch(action)
    dwell = HoverDwellController(schedule=scheduler.schedule, cancel=scheduler.cancel,
                                 dispatch=dispatch, snapshot=lambda: model.snapshot)
    return model, scheduler, actions, dwell, model.snapshot.spatial_scene.objects[0].object_id


def test_dwell_focus_observe_intervals_and_completion_use_canonical_actions():
    model, scheduler, actions, dwell, object_id = _dwell_setup()
    dwell.enter(object_id)
    assert actions == []
    focus_timer = dwell.pending_after_ids[-1]; scheduler.fire(focus_timer)
    assert actions == [SetFocusAction(object_id)]
    observe_timer = dwell.pending_after_ids[-1]; scheduler.fire(observe_timer)
    assert actions[-1] == ObserveFocusedObjectAction()
    for _ in range(5):
        scheduler.fire(dwell.pending_after_ids[-1])
    assert model.snapshot.focused_object_lod.current_lod == 3
    count = len(actions); scheduler.fire(dwell.pending_after_ids[-1])
    assert len(actions) == count
    assert "観察" in dwell.feedback


def test_dwell_cancel_generation_object_change_rejection_and_close_are_safe():
    model, scheduler, actions, dwell, object_id = _dwell_setup()
    dwell.enter(object_id); stale = dwell.pending_after_ids[-1]
    dwell.leave(); scheduler.fire(stale)
    assert actions == []
    dwell.enter(object_id); stale = dwell.pending_after_ids[-1]
    model.game_map.current = "plaza"; model.state.transition_location("plaza")
    model.snapshot = model._build_snapshot(); scheduler.fire(stale)
    assert actions == []
    dwell.close()
    assert dwell.closed and dwell.hovered_object_id is None


def test_same_focused_target_skips_duplicate_focus_and_redraw_does_not_reset():
    model, scheduler, actions, dwell, object_id = _dwell_setup()
    assert model.dispatch(SetFocusAction(object_id))
    dwell.enter(object_id); generation = dwell.generation
    model.redraw_only(); dwell.enter(object_id)
    assert dwell.generation == generation
    scheduler.fire(dwell.pending_after_ids[-1])
    assert SetFocusAction(object_id) not in actions
