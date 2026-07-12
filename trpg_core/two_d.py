"""Pure 2D layout/hit testing plus a lazily-created Tk placeholder client."""

from dataclasses import dataclass

from .input_actions import (
    ClearFocusAction, InspectFocusedObjectAction, ObserveFocusedObjectAction,
    SetFocusAction,
)
from .presentation import SceneSpatialView, SpatialCellView
from .spatial_input import (
    canonical_action_for_spatial_step, movement_action_from_step,
    movement_step_for_keyboard_code,
)
from .story_spatial import canonical_action_for_story_spatial_step

HOVER_FOCUS_DELAY_MS = 400
FIRST_OBSERVE_DELAY_MS = 700
OBSERVE_INTERVAL_MS = 700


@dataclass(frozen=True)
class PixelRect:
    left: int
    top: int
    width: int
    height: int

    def __post_init__(self):
        if any(type(v) is not int for v in (self.left, self.top, self.width, self.height)):
            raise ValueError("pixel rectangle values must be ints")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("pixel rectangle size must be positive")


@dataclass(frozen=True)
class TwoDLayout:
    window_width: int
    window_height: int
    map_rect: PixelRect
    side_panel_rect: PixelRect
    controls_rect: PixelRect
    cell_size: int
    grid_origin_x: int
    grid_origin_y: int
    scene_width: int
    scene_height: int


@dataclass(frozen=True)
class SidePanelLayout:
    status_top: int
    info_top: int
    exits_top: int
    scene_actions_top: int
    focus_actions_top: int
    button_height: int


def build_side_panel_layout(
    *, panel_height: int, exit_count: int, scene_action_count: int,
    focus_action_count: int, feedback: str, status_lines: int = 4,
) -> SidePanelLayout:
    if any(type(value) is not int or value < 0 for value in (
        panel_height, exit_count, scene_action_count, focus_action_count,
        status_lines,
    )):
        raise ValueError("panel layout counts must be non-negative ints")
    if type(feedback) is not str:
        raise ValueError("feedback must be text")
    status_top = 16
    info_top = status_top + status_lines * 18 + 12
    feedback_lines = min(3, max(1, (len(feedback) + 27) // 28))
    exits_top = info_top + 42 + feedback_lines * 16
    scene_actions_top = exits_top + 50 + min(exit_count, 4) * 18
    remaining = max(0, panel_height - scene_actions_top - 12)
    total_buttons = scene_action_count + focus_action_count
    button_height = max(22, min(30, (remaining - max(0, total_buttons - 1) * 4)
                                // max(1, total_buttons)))
    focus_actions_top = scene_actions_top + scene_action_count * (button_height + 4)
    return SidePanelLayout(
        status_top, info_top, exits_top, scene_actions_top,
        focus_actions_top, button_height,
    )


@dataclass(frozen=True)
class TwoDChoiceAction:
    key: str


@dataclass(frozen=True)
class TwoDCombatAction:
    command: str


def controls_text_for_phase(phase: str) -> str:
    controls = {
        "village": "WASD / Arrows: Move | Click: Focus | O: Observe | I: Inspect | Q: Quit\n対象にカーソルを合わせ続けると、自動で詳しく観察します。",
        "story": "WASD / Arrows: Move | Q: Quit",
        "combat": "戦闘actionをクリック | Q: Quit",
        "ending": "完了 | Q: Quit",
    }
    if phase not in controls:
        raise ValueError("unknown 2D session phase")
    return controls[phase]


def spatial_routes_text(scene: SceneSpatialView) -> str:
    if type(scene) is not SceneSpatialView or not scene.exits:
        raise ValueError("spatial route legend requires scene exits")
    entries = "\n".join(f"{item.marker} {item.label}" for item in scene.exits)
    if all(item.transition_kind == "story" for item in scene.exits):
        return f"進路\n{entries}\n\n番号のマスまでWASD／矢印キーで移動"
    return f"出口\n{entries}\n\n出口までWASD／矢印キーで移動"


def build_two_d_layout(*, window_width: int, window_height: int,
                       scene_width: int, scene_height: int) -> TwoDLayout:
    if any(type(v) is not int or v <= 0 for v in
           (window_width, window_height, scene_width, scene_height)):
        raise ValueError("layout sizes must be positive ints")
    controls_height = max(48, window_height // 8)
    body_height = window_height - controls_height
    if body_height <= 0:
        raise ValueError("window is too short")
    map_width = window_width * 3 // 5
    panel_width = window_width - map_width
    if map_width <= 0 or panel_width <= 0:
        raise ValueError("window is too narrow")
    cell_size = min(map_width // scene_width, body_height // scene_height)
    if cell_size <= 0:
        raise ValueError("scene does not fit in window")
    origin_x = (map_width - cell_size * scene_width) // 2
    origin_y = (body_height - cell_size * scene_height) // 2
    return TwoDLayout(
        window_width, window_height,
        PixelRect(0, 0, map_width, body_height),
        PixelRect(map_width, 0, panel_width, body_height),
        PixelRect(0, body_height, window_width, controls_height),
        cell_size, origin_x, origin_y, scene_width, scene_height,
    )


def pixel_rect_for_cell(layout: TwoDLayout, cell: SpatialCellView) -> PixelRect:
    if type(layout) is not TwoDLayout or type(cell) is not SpatialCellView:
        raise ValueError("exact layout and cell are required")
    if not 0 <= cell.x < layout.scene_width or not 0 <= cell.y < layout.scene_height:
        raise ValueError("cell is outside scene bounds")
    return PixelRect(layout.grid_origin_x + cell.x * layout.cell_size,
                     layout.grid_origin_y + cell.y * layout.cell_size,
                     layout.cell_size, layout.cell_size)


def spatial_object_at_pixel(scene: SceneSpatialView, layout: TwoDLayout, *, x: int, y: int):
    if type(x) is not int or type(y) is not int:
        raise ValueError("pixel coordinates must be ints")
    if not (layout.grid_origin_x <= x < layout.grid_origin_x + layout.cell_size * scene.width
            and layout.grid_origin_y <= y < layout.grid_origin_y + layout.cell_size * scene.height):
        return None
    cell = SpatialCellView((x - layout.grid_origin_x) // layout.cell_size,
                           (y - layout.grid_origin_y) // layout.cell_size)
    if scene.player_position == cell:
        return None
    return next((obj.object_id for obj in scene.objects
                 if obj.focus_candidate and obj.position == cell), None)


def normalized_keyboard_code(keysym: str, char: str = "") -> str | None:
    arrows = {"Up": "ArrowUp", "Left": "ArrowLeft", "Down": "ArrowDown", "Right": "ArrowRight"}
    if keysym in arrows:
        return arrows[keysym]
    return {"w": "KeyW", "a": "KeyA", "s": "KeyS", "d": "KeyD"}.get(char.lower())


class TwoDClientAdapter:
    def movement_action(self, position, keysym: str, char: str = ""):
        code = normalized_keyboard_code(keysym, char)
        step = movement_step_for_keyboard_code(code) if code is not None else None
        return None if position is None or step is None else movement_action_from_step(position, step)

    def canonical_movement_action(
        self, position, keysym: str, char: str = "", *, scene_id, definition,
    ):
        code = normalized_keyboard_code(keysym, char)
        step = movement_step_for_keyboard_code(code) if code is not None else None
        if position is None or step is None or definition is None:
            return None
        return canonical_action_for_spatial_step(
            current_scene_id=scene_id, current_position=position,
            step=step, definition=definition,
        )

    def canonical_story_movement_action(self, position, keysym: str, char: str = "", *, node_id, definition):
        code = normalized_keyboard_code(keysym, char)
        step = movement_step_for_keyboard_code(code) if code is not None else None
        if position is None or step is None or definition is None:
            return None
        return canonical_action_for_story_spatial_step(
            current_node_id=node_id, current_position=position,
            step=step, definition=definition,
        )

    def click_action(self, scene, layout, x, y):
        object_id = spatial_object_at_pixel(scene, layout, x=x, y=y)
        return None if object_id is None else SetFocusAction(object_id)

    @staticmethod
    def observe_action(): return ObserveFocusedObjectAction()
    @staticmethod
    def inspect_action(): return InspectFocusedObjectAction()
    @staticmethod
    def clear_focus_action(): return ClearFocusAction()


class TwoDSessionModel:
    """Headless GUI coordinator; only the shared village dispatcher mutates state."""

    def __init__(self, state):
        from .map import build_map
        self.state = state
        self.game_map = build_map(state.scenario, state.location)
        self.picked = []
        self.feedback = "Ready"
        self.adapter = TwoDClientAdapter()
        self.closed = False
        self.phase = "village"
        self.combat_encounter = None
        self.snapshot_builds = 0
        self._actions = ()
        self.snapshot = self._build_snapshot()

    def _build_snapshot(self):
        from .input_actions import ExploreAction, MoveToLocationAction
        from .presentation import ActionView, PresentationContext, build_map_view, build_render_snapshot
        from .session import _village_context
        from .world import location_world_object_id
        if self.phase != "village":
            node = self.state.scenario.node(self.state.node)
            actions = []
            enemies = ()
            if self.phase == "story":
                definition = self.state.story_spatial_definition_for_node(node.id)
                if definition is None:
                    actions = [(choice.label, TwoDChoiceAction(choice.key)) for choice in node.choices]
            elif self.phase == "combat":
                commands = ("attack", "magic", "herb", "flee")
                labels = {"attack": "攻撃", "magic": "魔法", "herb": "薬草", "flee": "逃走"}
                actions = [(labels[command], TwoDCombatAction(command))
                           for command in commands]
                from .presentation import build_enemy_views
                enemies = build_enemy_views(self.combat_encounter.enemies)
            self._actions = tuple(actions)
            objective = {
                "story": "物語を進める",
                "combat": "戦闘を解決する",
                "ending": "冒険は完了しました。Qで終了",
            }[self.phase]
            presentation_context = PresentationContext(
                scene_kind=self.phase, scene_id=node.id,
                scene_title=node.title or node.id,
                scene_text="".join(node.text),
                objective=objective,
                actions=tuple(ActionView(type(action).__name__, self.phase, label)
                              for label, action in actions),
                enemies=enemies,
            )
            self.snapshot_builds += 1
            return build_render_snapshot(
                self.state, presentation_context, active_game_map=None,
                lod_runtime=self.state.lod_runtime,
                story_spatial_definition=(
                    self.state.story_spatial_definition_for_node(node.id)
                    if self.phase == "story" else None
                ),
            )

        context = _village_context(self.state, self.game_map, self.picked)
        actions = []
        direction_labels = {"north": "北へ", "east": "東へ", "south": "南へ", "west": "西へ"}
        if self.state.spatial_definition_for_location(self.game_map.current) is None:
            for direction, object_id in context.move_destinations:
                destination = object_id.local_id[len("location/"):]
                label = f"{direction_labels[direction]} → {self.game_map.locations[destination].name}"
                actions.append((label, MoveToLocationAction(object_id)))
        if context.current_explore_key is not None:
            option = self.state.scenario.village_option(context.current_explore_key)
            actions.append((option.get("name", "Explore"), ExploreAction(context.current_explore_key)))
        actions.append(("周囲を見る", None))
        self._actions = tuple(actions)
        objective = f"支度をあと{max(0, self.state.scenario.village_pick_count-len(self.picked))}つ整える"
        presentation_context = PresentationContext(
            scene_kind="village", scene_id=self.game_map.current,
            scene_title=self.game_map.here().name, objective=objective,
            actions=tuple(ActionView("look" if action is None else type(action).__name__, "action", label)
                          for label, action in actions),
            map=build_map_view(self.game_map),
        )
        self.snapshot_builds += 1
        return build_render_snapshot(
            self.state, presentation_context, active_game_map=self.game_map,
            lod_runtime=self.state.lod_runtime,
        )

    @property
    def available_actions(self):
        return self._actions

    def dispatch(self, action):
        from .session import _apply_village_action
        try:
            if self.phase == "village":
                departed = _apply_village_action(
                    self.state, self.game_map, self.picked, action,
                )
                if departed:
                    self._enter_story_phase()
            elif self.phase == "story":
                from .input_actions import MovePlayerToPositionAction
                if type(action) is MovePlayerToPositionAction:
                    from .spatial_actions import apply_player_movement
                    apply_player_movement(self.state, action)
                else:
                    self._apply_story_choice(action)
            elif self.phase == "combat":
                self._apply_combat_action(action)
            else:
                raise ValueError("session has ended")
        except ValueError as exc:
            self.feedback = str(exc)
            return False
        self.feedback = "Accepted"
        self.snapshot = self._build_snapshot()
        return True

    def _enter_story_phase(self):
        from .session import _goto
        self.state.turn += 1
        _goto(self.state, self.state.scenario.start_node)
        self._sync_non_village_phase()

    def _sync_non_village_phase(self):
        node = self.state.scenario.node(self.state.node)
        if node.kind == "decision":
            self.phase = "story"
            self.combat_encounter = None
        elif node.kind == "combat":
            self.phase = "combat"
            from .combat import CombatEncounter
            from .session import has_recon
            self.combat_encounter = CombatEncounter(
                self.state, node.id, node.recon_free_first and has_recon(self.state),
            )
        else:
            self.phase = "ending"
            self.combat_encounter = None

    def _apply_story_choice(self, action):
        from .input_actions import StoryChoiceAction
        if type(action) not in (TwoDChoiceAction, StoryChoiceAction):
            raise ValueError("story phase requires a choice action")
        from .session import _handle_decision
        class Controller:
            def choice(self, _node, _options):
                return action.key
        _handle_decision(
            self.state, Controller(), self.state.scenario.node(self.state.node),
        )
        self._sync_non_village_phase()

    def _apply_combat_action(self, action):
        if type(action) is not TwoDCombatAction:
            raise ValueError("combat phase requires a combat action")
        from .input_actions import resolve_combat_command
        command = resolve_combat_command(action.command)
        if command is None:
            raise ValueError("invalid combat command")
        outcome = self.combat_encounter.step(command)
        if outcome is None:
            return
        from .session import _goto
        node = self.state.scenario.node(self.state.node)
        if outcome == "win":
            _goto(self.state, node.on_win)
        elif outcome == "fled":
            _goto(self.state, self.state.scenario.start_node)
        else:
            self.state.emit(type="ending", result="defeat")
            self.phase = "ending"
            return
        self._sync_non_village_phase()

    def activate_available_action(self, index: int):
        if type(index) is not int or not 0 <= index < len(self._actions):
            raise ValueError("available action index is out of range")
        _label, action = self._actions[index]
        if action is None:
            self.feedback = "周囲を見渡した"
            return True
        return self.dispatch(action)

    def key_action(self, keysym: str, char: str = ""):
        if keysym in {"q", "Q"} or char in {"q", "Q"}:
            self.closed = True
            return "quit"
        if self.phase != "village":
            if self.phase == "story":
                definition = self.state.story_spatial_definition_for_node(self.state.node)
                action = self.adapter.canonical_story_movement_action(
                    self.state.player_position, keysym, char,
                    node_id=self.state.node, definition=definition,
                )
                if action is not None:
                    return action
            if normalized_keyboard_code(keysym, char) is not None:
                self.feedback = "Spatial movement is unavailable in this phase"
            return None
        if keysym == "Escape": return ClearFocusAction()
        if char.lower() == "o": return ObserveFocusedObjectAction()
        if char.lower() == "i": return InspectFocusedObjectAction()
        from .world import location_world_object_id
        definition = self.state.spatial_definition_for_location(self.state.location)
        scene_id = (
            location_world_object_id(self.state.scenario.id, self.state.location)
            if self.state.location is not None else None
        )
        action = self.adapter.canonical_movement_action(
            self.state.player_position, keysym, char,
            scene_id=scene_id, definition=definition,
        )
        if action is None and normalized_keyboard_code(keysym, char) is not None:
            self.feedback = "No spatial player position"
        return action

    def handle_key(self, keysym: str, char: str = ""):
        action = self.key_action(keysym, char)
        if action == "quit" or action is None: return action
        self.dispatch(action)
        return action

    def handle_click(self, layout, x, y):
        scene = self.snapshot.spatial_scene
        if scene is None: return None
        action = self.adapter.click_action(scene, layout, x, y)
        if action is not None: self.dispatch(action)
        return action

    def redraw_only(self):
        return self.snapshot


class HoverDwellController:
    """Client-only cancellable dwell policy; time never enters engine state."""

    def __init__(self, *, schedule, cancel, dispatch, snapshot, active=lambda: True):
        self.schedule = schedule
        self.cancel_timer = cancel
        self.dispatch = dispatch
        self.snapshot = snapshot
        self.active = active
        self.hovered_object_id = None
        self.generation = 0
        self.pending_after_ids = []
        self.focus_dispatched = False
        self.observe_count = 0
        self.dispatch_in_flight = False
        self.scene_id = None
        self.feedback = ""
        self.closed = False

    def _eligible(self, object_id):
        snap = self.snapshot()
        scene = snap.spatial_scene
        return (scene is not None and snap.scene_id == self.scene_id and self.active()
                and any(obj.object_id == object_id and obj.focus_candidate for obj in scene.objects))

    def _schedule(self, delay, callback, generation, object_id):
        timer_id = self.schedule(delay, lambda: callback(generation, object_id))
        self.pending_after_ids.append(timer_id)

    def enter(self, object_id):
        if object_id == self.hovered_object_id and self._eligible(object_id):
            return
        self.leave()
        if object_id is None:
            return
        snap = self.snapshot(); self.scene_id = snap.scene_id
        if not self._eligible(object_id):
            return
        self.hovered_object_id = object_id
        self.generation += 1
        self.feedback = "観察中…"
        self._schedule(HOVER_FOCUS_DELAY_MS, self._focus_due, self.generation, object_id)

    def leave(self):
        for timer_id in self.pending_after_ids:
            self.cancel_timer(timer_id)
        self.pending_after_ids.clear()
        self.hovered_object_id = None
        self.generation += 1
        self.focus_dispatched = False
        self.observe_count = 0

    def _valid(self, generation, object_id):
        return (not self.closed and generation == self.generation
                and object_id == self.hovered_object_id
                and not self.dispatch_in_flight and self._eligible(object_id))

    def _focus_due(self, generation, object_id):
        if not self._valid(generation, object_id): return
        snap = self.snapshot()
        serialized = f"{object_id.scenario_id}:{object_id.local_id}"
        if snap.focused_object_id != serialized:
            self.dispatch_in_flight = True
            accepted = self.dispatch(SetFocusAction(object_id))
            self.dispatch_in_flight = False
            if not accepted:
                self.feedback = "観察を開始できません"
                self.leave(); return
        self.focus_dispatched = True
        self.feedback = "さらに目を凝らしています…"
        self._schedule(FIRST_OBSERVE_DELAY_MS, self._observe_due, generation, object_id)

    def _observe_due(self, generation, object_id):
        if not self._valid(generation, object_id) or not self.focus_dispatched: return
        view = self.snapshot().focused_object_lod
        if view is None or not view.has_more_observable_detail:
            self.feedback = "現在見える範囲を観察しました"
            return
        self.dispatch_in_flight = True
        accepted = self.dispatch(ObserveFocusedObjectAction())
        self.dispatch_in_flight = False
        if not accepted:
            self.feedback = "観察を続けられません"
            self.leave(); return
        self.observe_count += 1
        self.feedback = "さらに目を凝らしています…"
        if self._valid(generation, object_id):
            self._schedule(OBSERVE_INTERVAL_MS, self._observe_due, generation, object_id)

    def close(self):
        self.closed = True
        self.leave()


def make_available_action_callback(model, index, redraw, refocus):
    """Bind one stable action index without Tk loop-variable late binding."""
    def callback():
        model.activate_available_action(index)
        redraw()
        refocus()
    return callback


def run_two_d_session(seed: int, scenario_id: str) -> None:
    try:
        import tkinter as tk
    except ImportError as exc:
        raise RuntimeError("Tkinter is unavailable") from exc
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError("2D display is unavailable") from exc
    from .scenario_loader import load_scenario
    from .session import GameState
    model = TwoDSessionModel(GameState(seed, scenario=load_scenario(scenario_id)))
    root.title(f"Perceptive World — {scenario_id} — seed {seed}")
    root.minsize(760, 620)
    canvas = tk.Canvas(root, width=960, height=640, background="#20242a", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    buttons = []
    button_signature = None
    current_layout = None
    dwell = None

    def redraw(_event=None):
        nonlocal current_layout, buttons, button_signature
        canvas.delete("all")
        width, height = max(root.winfo_width(), 640), max(root.winfo_height(), 480)
        snap = model.snapshot
        scene = snap.spatial_scene
        sw, sh = ((scene.width, scene.height) if scene is not None else (7, 5))
        current_layout = build_two_d_layout(window_width=width, window_height=height,
                                            scene_width=sw, scene_height=sh)
        if scene is None:
            canvas.create_text(current_layout.map_rect.width//2, current_layout.map_rect.height//2,
                               text=snap.scene_text or "No active spatial map", fill="white",
                               width=max(200, current_layout.map_rect.width-48))
        else:
            walkable = set(scene.walkable_cells)
            for y in range(scene.height):
                for x in range(scene.width):
                    cell = SpatialCellView(x, y); rect = pixel_rect_for_cell(current_layout, cell)
                    canvas.create_rectangle(rect.left, rect.top, rect.left+rect.width, rect.top+rect.height,
                                            fill="#59636e" if cell in walkable else "#282d33", outline="#15181c")
            for obj in scene.objects:
                rect = pixel_rect_for_cell(current_layout, obj.position)
                focused = model.snapshot.focused_object_id == f"{obj.object_id.scenario_id}:{obj.object_id.local_id}"
                canvas.create_oval(rect.left+8, rect.top+8, rect.left+rect.width-8, rect.top+rect.height-8,
                                   fill="#b28b45", outline="#ffffff" if focused else "#403018", width=4 if focused else 2)
                canvas.create_text(
                    rect.left+rect.width//2, rect.top+rect.height//2,
                    text=obj.glyph, fill="white", font=("TkDefaultFont", 14, "bold"),
                )
                if dwell is not None and dwell.hovered_object_id == obj.object_id:
                    canvas.create_rectangle(rect.left+3, rect.top+3, rect.left+rect.width-3, rect.top+rect.height-3,
                                            outline="#8fd3ff", width=2)
            for exit_ in scene.exits:
                rect = pixel_rect_for_cell(current_layout, exit_.position)
                canvas.create_rectangle(
                    rect.left+4, rect.top+4, rect.left+rect.width-4,
                    rect.top+rect.height-4, outline="#8fd3ff", width=3,
                )
                canvas.create_text(
                    rect.left+rect.width//2, rect.top+rect.height//2,
                    text=exit_.marker, fill="white",
                    font=("TkDefaultFont", 13, "bold"),
                )
            if scene.player_position is not None:
                rect = pixel_rect_for_cell(current_layout, scene.player_position)
                canvas.create_text(rect.left+rect.width//2, rect.top+rect.height//2, text="@", fill="white", font=("TkDefaultFont", 18, "bold"))
        pos = "なし" if snap.spatial_scene is None or snap.spatial_scene.player_position is None else f"x={snap.spatial_scene.player_position.x}, y={snap.spatial_scene.player_position.y}"
        focus = next((obj.label for obj in snap.world_objects if obj.object_id == snap.focused_object_id), "なし")
        lod = "なし" if snap.focused_object_lod is None else str(snap.focused_object_lod.current_lod)
        panel_x = current_layout.side_panel_rect.left + 18
        feedback = dwell.feedback if dwell is not None and dwell.feedback else model.feedback
        focus_specs = ()
        focused = snap.focused_object_id is not None
        complete = snap.focused_object_lod is not None and not snap.focused_object_lod.has_more_observable_detail
        if scene is not None and model.phase == "village":
            focus_specs = (
                ("今すぐ観察する", ObserveFocusedObjectAction(), focused and not complete),
                ("詳しく調べる", InspectFocusedObjectAction(), focused),
                ("注目を解除", ClearFocusAction(), focused),
            )
        if model.phase == "combat":
            player = snap.player
            status_lines = 6 + len(snap.enemies)
            status_text = (
                f"Scene: {snap.scene_title or 'なし'}\nPlayer\n{player.name}\n"
                f"HP {player.hp} / {player.hp_max}\nMP {player.mp} / {player.mp_max}\n"
                f"薬草 {player.recovery_item_count}\nEnemies\n"
                + "\n".join(
                    f"{enemy.name}  HP {max(0, enemy.hp)} / {enemy.hp_max}"
                    for enemy in snap.enemies
                )
            )
        elif model.phase == "village":
            status_lines = 4
            status_text = (
                f"Scene: {snap.scene_title or 'なし'}\nPlayer: {pos}\n"
                f"Focus: {focus}\nLOD: {lod}"
            )
        else:
            status_lines = 1
            status_text = f"Scene: {snap.scene_title or 'なし'}"
        panel_layout = build_side_panel_layout(
            panel_height=current_layout.side_panel_rect.height,
            exit_count=0 if scene is None else len(scene.exits),
            scene_action_count=len(model.available_actions),
            focus_action_count=len(focus_specs), feedback=feedback,
            status_lines=status_lines,
        )
        canvas.create_text(
            panel_x, panel_layout.status_top, anchor="nw", fill="white",
            text=status_text,
        )
        clipped_feedback = feedback if len(feedback) <= 84 else feedback[:81] + "..."
        canvas.create_text(
            panel_x, panel_layout.info_top, anchor="nw", fill="white",
            width=max(120, current_layout.side_panel_rect.width-36),
            text=f"Objective\n{snap.objective}\nFeedback\n{clipped_feedback}",
        )
        if scene is not None and scene.exits:
            canvas.create_text(
                panel_x, panel_layout.exits_top, anchor="nw", fill="white",
                text=spatial_routes_text(scene),
            )
        signature = (
            tuple(label for label, _action in model.available_actions),
            tuple((label, enabled) for label, _action, enabled in focus_specs),
        )
        if signature != button_signature:
            for button in buttons:
                button.destroy()
            buttons = []
            for index, (label, _action) in enumerate(model.available_actions):
                buttons.append(tk.Button(
                    root, text=label, anchor="w", justify="left",
                    foreground="#111111", background="#f2f2f2",
                    activeforeground="#000000", activebackground="#d9e8ff",
                    command=make_available_action_callback(
                        model, index, redraw, root.focus_force,
                    ),
                ))
            for label, action, enabled in focus_specs:
                buttons.append(tk.Button(
                    root, text=label, foreground="#111111", background="#f2f2f2",
                    state="normal" if enabled else "disabled",
                    command=lambda a=action: (
                        model.dispatch(a), redraw(), root.focus_force(),
                    ),
                ))
            button_signature = signature
        y = panel_layout.scene_actions_top
        for button in buttons[:len(model.available_actions)]:
            button.place(
                x=panel_x, y=y,
                width=max(140, current_layout.side_panel_rect.width-36),
                height=panel_layout.button_height,
            )
            y += panel_layout.button_height + 4
        y = panel_layout.focus_actions_top
        for button in buttons[len(model.available_actions):]:
            button.place(
                x=panel_x, y=y,
                width=max(140, current_layout.side_panel_rect.width-36),
                height=panel_layout.button_height,
            )
            y += panel_layout.button_height + 4
        canvas.create_text(width//2, current_layout.controls_rect.top+current_layout.controls_rect.height//2,
                           text=controls_text_for_phase(model.phase), fill="white")

    def on_key(event):
        old_scene = model.snapshot.scene_id
        result = model.handle_key(event.keysym, event.char)
        if result == "quit": dwell.close(); root.destroy()
        else:
            if model.snapshot.scene_id != old_scene:
                dwell.leave()
            redraw(); root.focus_force()

    def on_click(event):
        if current_layout is not None: model.handle_click(current_layout, event.x, event.y)
        redraw(); root.focus_force()

    def on_motion(event):
        if current_layout is None or model.snapshot.spatial_scene is None:
            dwell.leave(); redraw(); return
        object_id = spatial_object_at_pixel(model.snapshot.spatial_scene, current_layout,
                                            x=event.x, y=event.y)
        dwell.enter(object_id)
        redraw()

    def dispatch_dwell(action):
        accepted = model.dispatch(action)
        redraw()
        return accepted

    dwell = HoverDwellController(
        schedule=root.after, cancel=root.after_cancel, dispatch=dispatch_dwell,
        snapshot=lambda: model.snapshot,
        active=lambda: root.focus_displayof() is not None,
    )

    root.bind("<Key>", on_key)
    canvas.bind("<Button-1>", on_click)
    canvas.bind("<Motion>", on_motion)
    canvas.bind("<Leave>", lambda _event: (dwell.leave(), redraw()))
    root.bind("<FocusOut>", lambda _event: dwell.leave())
    def on_configure(event):
        if event.widget is root or event.widget is canvas:
            redraw()

    root.bind("<Configure>", on_configure)
    root.bind("q", on_key); root.bind("Q", on_key)
    def close_window():
        dwell.close(); root.destroy()
    root.protocol("WM_DELETE_WINDOW", close_window)
    root.update_idletasks(); redraw(); root.focus_force()
    root.mainloop()
