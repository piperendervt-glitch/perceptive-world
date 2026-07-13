"""UIに依存しない、読み取り専用の表示モデル。

``RenderSnapshot`` は画面を組み立てるための一時的な値であり、
``GameState.snapshot()`` とは別物である。save、replay、fixture、GameStateの
復元には使用せず、端末サイズ・ANSI・入力装置などのUI固有状態も保持しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .knowledge import goblin_knowledge_catalog
from .lod import derive_current_lod
from .lod_actions import (
    LodRuntimeState,
    initial_lod_progress,
    lod_progress_for_world_object,
)
from .lod_content import lod_content_for_world_object, visible_facts_for_lod
from .rules import effect_damage_bonus, effect_hit_bonus, has_recon, modifier
from .world import (
    WorldFact,
    WorldObjectId,
    serialize_world_object_id,
    world_objects_for_current_scene,
)


def _exact_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be a non-empty untrimmed string")
    return value


@dataclass(frozen=True)
class VisibleWorldFactView:
    key: str
    value: str
    label: str

    def __post_init__(self) -> None:
        _exact_text(self.key, "key")
        _exact_text(self.value, "value")
        _exact_text(self.label, "label")


@dataclass(frozen=True)
class FocusedObjectLodView:
    object_id: WorldObjectId
    current_lod: int
    visible_facts: tuple[VisibleWorldFactView, ...]
    has_more_observable_detail: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, WorldObjectId):
            raise ValueError("object_id must be a WorldObjectId")
        if type(self.current_lod) is not int or self.current_lod < 0:
            raise ValueError("current_lod must be a non-negative int")
        if type(self.visible_facts) is not tuple:
            raise ValueError("visible_facts must be a tuple")
        if type(self.has_more_observable_detail) is not bool:
            raise ValueError("has_more_observable_detail must be a bool")
        keys = set()
        for fact in self.visible_facts:
            if not isinstance(fact, VisibleWorldFactView):
                raise ValueError("visible_facts must contain VisibleWorldFactView values")
            if fact.key in keys:
                raise ValueError(f"duplicate visible fact key: {fact.key}")
            keys.add(fact.key)


_OBJECT_PRESENTATION_LABELS = {
    WorldObjectId("goblin", "location/well"): "古井戸",
    WorldObjectId("goblin", "location/shrine"): "古い祠",
    WorldObjectId("goblin", "location/lookout"): "物見櫓",
    WorldObjectId("goblin", "location/herbhut"): "薬草小屋",
    WorldObjectId("goblin", "location/elderhouse"): "村長の家",
}

_KNOWLEDGE_PRESENTATION_LABELS = {
    "well.shape.well_like": "井戸らしき形",
    "well.material.stone": "石造り",
    "well.age.old": "古い",
    "well.pulley.recent": "新しい滑車",
    "well.rope.worn": "擦り切れた縄",
    "well.mark.faded_emblem": "消えかけた紋章",
    "shrine.shape.small_shrine": "小さな祠",
    "shrine.material.weathered_stone": "風雨にさらされた石造り",
    "shrine.offering.kept_clean": "供物台は清められている",
    "shrine.condition.quietly_usable": "静かに祈りを捧げられる",
    "lookout.shape.lookout_tower": "物見櫓",
    "lookout.material.timber": "木造",
    "lookout.view.forest_edge_visible": "森の縁を見渡せる",
    "lookout.condition.stable_vantage": "足場は見張りに使える",
    "herbhut.shape.small_hut": "小さな小屋",
    "herbhut.scent.dried_herbs": "乾燥薬草の香り",
    "herbhut.stock.prepared_bundles": "薬草の束が用意されている",
    "herbhut.condition.carefully_sorted": "薬草は丁寧に選別されている",
    "elderhouse.shape.large_house": "大きな家",
    "elderhouse.material.old_timber": "年季の入った木造",
    "elderhouse.records.village_notes": "村の記録が置かれている",
    "elderhouse.condition.orderly_meeting_place": "話を聞けるよう整えられている",
    "memory.well.faded_emblem": "消えかけた紋章の記憶",
    "memory.shrine.blessing_site": "祈りを捧げられる場所の記憶",
    "memory.lookout.surveyed": "物見櫓から見渡した記憶",
    "memory.herbhut.supplies": "用意された薬草の記憶",
    "memory.elder.intel": "村の記録を確かめた記憶",
}


def presentation_label_for_object(object_id: WorldObjectId) -> str:
    if not isinstance(object_id, WorldObjectId):
        raise ValueError("exact WorldObjectId is required")
    mapped = _OBJECT_PRESENTATION_LABELS.get(object_id)
    if mapped is None:
        raise ValueError("no presentation label mapping for object")
    return mapped


def knowledge_presentation_label(label_key: str) -> str:
    """Resolve a closed knowledge label without exposing a raw-key fallback."""

    if not isinstance(label_key, str) or not label_key or label_key != label_key.strip():
        raise ValueError("exact knowledge label key is required")
    label = _KNOWLEDGE_PRESENTATION_LABELS.get(label_key)
    if label is None:
        raise ValueError("no knowledge presentation label mapping")
    return label


def visible_world_fact_view(object_id: WorldObjectId, fact: WorldFact) -> VisibleWorldFactView:
    if not isinstance(object_id, WorldObjectId) or not isinstance(fact, WorldFact):
        raise ValueError("exact WorldObjectId and WorldFact are required")
    if object_id.scenario_id != "goblin":
        raise ValueError("no presentation label mapping for object")
    knowledge_object = goblin_knowledge_catalog().object(object_id)
    if knowledge_object is None:
        raise ValueError("no presentation label mapping for object")
    spec = knowledge_object.fact(fact.key)
    if spec is None or spec.value != fact.value:
        raise ValueError("no exact presentation label mapping for fact")
    return VisibleWorldFactView(
        fact.key,
        fact.value,
        knowledge_presentation_label(spec.label_key),
    )


def focused_object_lod_view(
    *, focused_object_id: WorldObjectId | None,
    lod_runtime: LodRuntimeState | None,
) -> FocusedObjectLodView | None:
    if focused_object_id is None or lod_runtime is None:
        return None
    if not isinstance(focused_object_id, WorldObjectId):
        raise ValueError("focused_object_id must be a WorldObjectId or None")
    if not isinstance(lod_runtime, LodRuntimeState):
        raise ValueError("lod_runtime must be a LodRuntimeState or None")
    content = lod_content_for_world_object(focused_object_id)
    if content is None:
        return None
    progress = lod_progress_for_world_object(lod_runtime, focused_object_id)
    if progress is None:
        progress = initial_lod_progress(content)
    current_lod = derive_current_lod(content.lod_spec, progress.attention, progress.lod_state)
    visible = visible_facts_for_lod(content, current_lod)
    return FocusedObjectLodView(
        focused_object_id,
        current_lod,
        tuple(visible_world_fact_view(focused_object_id, fact) for fact in visible.facts),
        current_lod < min(content.lod_spec.max_lod, progress.lod_state.unlocked_lod_cap),
    )


@dataclass(frozen=True)
class AttributeView:
    key: str
    value: int
    modifier: int


@dataclass(frozen=True)
class PlayerView:
    hp: int
    hp_max: int
    mp: int
    mp_max: int
    recovery_item_name: str
    recovery_item_count: int
    pending_recovery_count: int = 0
    attributes: tuple[AttributeView, ...] = field(default_factory=tuple)
    buffs: tuple[str, ...] = field(default_factory=tuple)
    name: str = "H"
    physical_damage_bonus: int = 0
    global_hit_bonus: int = 0
    watcher_hit_bonus: int = 0
    chief_hit_bonus: int = 0
    recon_active: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", tuple(self.attributes))
        object.__setattr__(self, "buffs", tuple(self.buffs))


@dataclass(frozen=True)
class ActionView:
    canonical_command: str
    kind: str
    label: str
    detail: str | None = None
    enabled: bool = True


@dataclass(frozen=True)
class EnemyView:
    key: str
    name: str
    hp: int
    alive: bool
    auto_target: bool = False
    hp_max: int = 0


@dataclass(frozen=True)
class WorldObjectView:
    object_id: str
    kind: str
    label: str


@dataclass(frozen=True)
class SpatialCellView:
    x: int
    y: int

    def __post_init__(self):
        if type(self.x) is not int or type(self.y) is not int:
            raise ValueError("spatial cell coordinates must be ints")


@dataclass(frozen=True)
class SpatialObjectView:
    object_id: WorldObjectId
    label: str
    position: SpatialCellView
    blocks_movement: bool
    focus_candidate: bool
    glyph: str = "?"
    visual_asset_key: str | None = None

    def __post_init__(self):
        if type(self.label) is not str or not self.label:
            raise ValueError("spatial object label must be non-empty")
        if type(self.glyph) is not str or not self.glyph:
            raise ValueError("spatial object glyph must be non-empty")
        if self.visual_asset_key is not None and (
            type(self.visual_asset_key) is not str or not self.visual_asset_key
        ):
            raise ValueError("visual_asset_key must be non-empty text or None")


def visual_asset_key_for_object(object_id: WorldObjectId, lod_runtime: LodRuntimeState | None) -> str | None:
    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    if lod_runtime is not None and not isinstance(lod_runtime, LodRuntimeState):
        raise ValueError("lod_runtime must be a LodRuntimeState or None")
    asset_name = {
        WorldObjectId("goblin", "location/well"): "well",
        WorldObjectId("goblin", "location/shrine"): "shrine",
        WorldObjectId("goblin", "location/lookout"): "lookout",
        WorldObjectId("goblin", "location/herbhut"): "herbhut",
        WorldObjectId("goblin", "location/elderhouse"): "elderhouse",
    }.get(object_id)
    if asset_name is None:
        return None
    content = lod_content_for_world_object(object_id)
    progress = None if lod_runtime is None else lod_progress_for_world_object(lod_runtime, object_id)
    if progress is None:
        progress = initial_lod_progress(content)
    lod = derive_current_lod(content.lod_spec, progress.attention, progress.lod_state)
    return f"goblin/{asset_name}/lod{lod}"


_LANDMARK_GLYPHS = {
    "村の広場": "広",
    "古井戸": "井",
    "物見櫓": "櫓",
    "薬草小屋": "薬",
    "古い祠": "祠",
    "村長の家": "長",
    "村の出口（森へ）": "門",
}


def landmark_glyph_for_label(label: str) -> str:
    if type(label) is not str or not label:
        raise ValueError("landmark label must be non-empty")
    return _LANDMARK_GLYPHS.get(label, label[0])


@dataclass(frozen=True)
class SpatialExitView:
    position: SpatialCellView
    label: str
    transition_kind: str
    marker: str = "E"

    def __post_init__(self):
        if type(self.position) is not SpatialCellView:
            raise ValueError("position must be a SpatialCellView")
        if type(self.label) is not str or not self.label:
            raise ValueError("label must be non-empty text")
        if self.transition_kind not in {"move", "depart", "story"}:
            raise ValueError("transition_kind must be move, depart, or story")
        if type(self.marker) is not str or not self.marker:
            raise ValueError("marker must be non-empty text")


_STORY_TRIGGER_MARKERS = tuple("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")


def story_trigger_marker(index: int) -> str:
    if type(index) is not int or index < 0:
        raise ValueError("story trigger index must be a non-negative int")
    return _STORY_TRIGGER_MARKERS[index] if index < len(_STORY_TRIGGER_MARKERS) else str(index + 1)


@dataclass(frozen=True)
class SceneSpatialView:
    width: int
    height: int
    walkable_cells: tuple[SpatialCellView, ...]
    blocked_cells: tuple[SpatialCellView, ...]
    player_position: SpatialCellView | None
    objects: tuple[SpatialObjectView, ...]
    exits: tuple[SpatialExitView, ...] = ()

    def __post_init__(self):
        if type(self.width) is not int or self.width <= 0 or type(self.height) is not int or self.height <= 0:
            raise ValueError("spatial dimensions must be positive ints")
        for name in ("walkable_cells", "blocked_cells", "objects", "exits"):
            if type(getattr(self, name)) is not tuple:
                raise ValueError(f"{name} must be a tuple")
        if len(set(self.walkable_cells)) != len(self.walkable_cells):
            raise ValueError("duplicate walkable cell")
        if len(set(self.blocked_cells)) != len(self.blocked_cells):
            raise ValueError("duplicate blocked cell")
        ids = tuple(item.object_id for item in self.objects)
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate spatial object ID")
        exit_cells = tuple(item.position for item in self.exits)
        if len(set(exit_cells)) != len(exit_cells):
            raise ValueError("duplicate spatial exit cell")


@dataclass(frozen=True)
class PreparationView:
    selected_keys: tuple[str, ...] = field(default_factory=tuple)
    selected_count: int = 0
    required_count: int = 0
    pending_recovery_count: int = 0
    ready_to_depart: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "selected_keys", tuple(self.selected_keys))


@dataclass(frozen=True)
class MapExitView:
    direction: str
    destination: str
    label: str


@dataclass(frozen=True)
class MapView:
    current_location: str | None
    current_label: str
    exits: tuple[MapExitView, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "exits", tuple(self.exits))


@dataclass(frozen=True)
class PresentationContext:
    """GameStateに属さない、現在の場面だけの表示情報。"""

    scene_kind: str = ""
    scene_id: str | None = None
    scene_title: str = ""
    scene_text: str = ""
    objective: str = ""
    recovery_item_name: str = "薬草"
    pending_recovery_count: int = 0
    actions: tuple[ActionView, ...] = field(default_factory=tuple)
    enemies: tuple[EnemyView, ...] = field(default_factory=tuple)
    preparation: PreparationView | None = None
    map: MapView | None = None
    recent_messages: tuple[str, ...] = field(default_factory=tuple)
    ending: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "enemies", tuple(self.enemies))
        object.__setattr__(self, "recent_messages", tuple(self.recent_messages))


@dataclass(frozen=True)
class RenderSnapshot:
    """表示専用のimmutable値。save/replay/fixtureや状態復元には使用しない。"""

    scenario_id: str
    scene_id: str | None
    scene_kind: str
    scene_title: str
    scene_text: str
    turn: int
    objective: str
    player: PlayerView
    actions: tuple[ActionView, ...] = field(default_factory=tuple)
    enemies: tuple[EnemyView, ...] = field(default_factory=tuple)
    preparation: PreparationView | None = None
    map: MapView | None = None
    recent_messages: tuple[str, ...] = field(default_factory=tuple)
    ending: str | None = None
    world_objects: tuple[WorldObjectView, ...] = field(default_factory=tuple)
    focused_object_id: str | None = None
    focused_object_lod: FocusedObjectLodView | None = None
    spatial_scene: SceneSpatialView | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "enemies", tuple(self.enemies))
        object.__setattr__(self, "recent_messages", tuple(self.recent_messages))
        object.__setattr__(self, "world_objects", tuple(self.world_objects))


def build_render_snapshot(
    state: Any,
    context: PresentationContext | None = None,
    *,
    active_game_map: Any | None = None,
    lod_runtime: LodRuntimeState | None = None,
    story_spatial_definition: Any | None = None,
) -> RenderSnapshot:
    """GameState相当の値を読み、ゲーム状態を変更せず表示用コピーを返す。

    ``state`` はduck typingで扱うため、sessionモジュールへの実行時依存を作らない。
    context内のコレクションもtupleへコピーされ、元の可変コレクションを保持しない。
    """

    context = context or PresentationContext()
    attributes = tuple(
        AttributeView(key=key, value=int(getattr(state, key)),
                      modifier=modifier(int(getattr(state, key))))
        for key in ("str", "mag", "vit")
    )
    player = PlayerView(
        hp=int(state.hp),
        hp_max=int(state.hp_max),
        mp=int(state.mp),
        mp_max=int(state.mp_max),
        recovery_item_name=str(context.recovery_item_name),
        recovery_item_count=int(state.herbs),
        pending_recovery_count=int(context.pending_recovery_count),
        attributes=attributes,
        buffs=tuple(str(label) for label in state.buff_labels),
        physical_damage_bonus=effect_damage_bonus(state, "physical"),
        global_hit_bonus=effect_hit_bonus(state, "__no_target__"),
        watcher_hit_bonus=(
            effect_hit_bonus(state, "sentry")
            - effect_hit_bonus(state, "__no_target__")
        ),
        chief_hit_bonus=(
            effect_hit_bonus(state, "chief")
            - effect_hit_bonus(state, "__no_target__")
        ),
        recon_active=has_recon(state),
    )
    focus_state = getattr(state, "focus_state", None)
    focused_id = getattr(focus_state, "focused_object_id", None)
    world_objects: tuple[WorldObjectView, ...] = ()
    focused_object_id = None
    spatial_scene = None
    if active_game_map is not None:
        scene_objects = world_objects_for_current_scene(
            scenario_id=state.scenario.id, game_map=active_game_map,
        )
        world_objects = tuple(
            WorldObjectView(
                object_id=serialize_world_object_id(item.spec.object_id),
                kind=item.spec.kind,
                label=item.spec.label,
            )
            for item in scene_objects
            if item.visibility.perceived
        )
        if focused_id is not None:
            focusable_ids = tuple(
                item.spec.object_id
                for item in scene_objects
                if item.visibility.focus_candidate
            )
            if focused_id not in focusable_ids:
                raise ValueError("focused object is not in the current scene")
            focused_object_id = serialize_world_object_id(focused_id)
        from .spatial import SceneCell, is_blocked_cell
        definition = state.spatial_definition_for_location(active_game_map.current)
        if definition is not None:
            spec = definition.spec
            visible_by_id = {item.spec.object_id: item for item in scene_objects
                             if item.visibility.exists_in_scene and item.visibility.perceived}
            objects = tuple(
                SpatialObjectView(
                    placement.object_id,
                    visible_by_id[placement.object_id].spec.label,
                    SpatialCellView(placement.position.x, placement.position.y),
                    placement.blocks_movement,
                    visible_by_id[placement.object_id].visibility.focus_candidate,
                    landmark_glyph_for_label(
                        visible_by_id[placement.object_id].spec.label,
                    ),
                    visual_asset_key_for_object(placement.object_id, lod_runtime),
                )
                for placement in spec.object_placements
                if placement.object_id in visible_by_id
            )
            blocked = tuple(
                SpatialCellView(x, y)
                for y in range(spec.bounds.height)
                for x in range(spec.bounds.width)
                if is_blocked_cell(spec, SceneCell(x, y))
            )
            position = getattr(state, "player_position", None)
            from .spatial import DepartSceneExit, MoveToSceneExit
            exits = []
            for exit_ in definition.exits:
                if type(exit_.transition) is MoveToSceneExit:
                    local_id = exit_.transition.destination_scene_id.local_id
                    destination = local_id.removeprefix("location/")
                    if destination not in active_game_map.locations:
                        raise ValueError("spatial exit destination is not in map")
                    label = active_game_map.locations[destination].name
                    kind = "move"
                elif type(exit_.transition) is DepartSceneExit:
                    label = "森の道へ"
                    kind = "depart"
                else:
                    raise ValueError("unsupported spatial exit transition")
                exits.append(SpatialExitView(
                    SpatialCellView(exit_.cell.x, exit_.cell.y), label, kind,
                ))
            spatial_scene = SceneSpatialView(
                spec.bounds.width, spec.bounds.height,
                tuple(SpatialCellView(cell.x, cell.y) for cell in spec.walkable_cells),
                blocked,
                None if position is None else SpatialCellView(position.x, position.y),
                objects,
                tuple(exits),
            )
    elif story_spatial_definition is not None:
        from .spatial import SceneCell, is_blocked_cell
        definition = story_spatial_definition
        spec = definition.spec
        blocked = tuple(
            SpatialCellView(x, y)
            for y in range(spec.bounds.height)
            for x in range(spec.bounds.width)
            if is_blocked_cell(spec, SceneCell(x, y))
        )
        trigger_labels = {
            choice.key: choice.label
            for choice in state.scenario.node(definition.node_id).choices
        }
        exits = tuple(SpatialExitView(
            SpatialCellView(trigger.cell.x, trigger.cell.y),
            trigger_labels[trigger.transition.choice_key], "story",
            story_trigger_marker(index),
        ) for index, trigger in enumerate(definition.triggers))
        position = getattr(state, "player_position", None)
        spatial_scene = SceneSpatialView(
            spec.bounds.width, spec.bounds.height,
            tuple(SpatialCellView(cell.x, cell.y) for cell in spec.walkable_cells),
            blocked,
            None if position is None else SpatialCellView(position.x, position.y),
            (), exits,
        )
    elif focused_id is not None:
        raise ValueError("focused object requires an active map scene")
    return RenderSnapshot(
        scenario_id=str(state.scenario.id),
        scene_id=context.scene_id,
        scene_kind=str(context.scene_kind),
        scene_title=str(context.scene_title),
        scene_text=str(context.scene_text),
        turn=int(state.turn),
        objective=str(context.objective),
        player=player,
        actions=tuple(context.actions),
        enemies=tuple(context.enemies),
        preparation=context.preparation,
        map=context.map,
        recent_messages=tuple(str(message) for message in context.recent_messages),
        ending=context.ending,
        world_objects=world_objects,
        focused_object_id=focused_object_id,
        focused_object_lod=focused_object_lod_view(
            focused_object_id=focused_id, lod_runtime=lod_runtime,
        ),
        spatial_scene=spatial_scene,
    )


def build_enemy_views(enemies: Iterable[Any]) -> tuple[EnemyView, ...]:
    """既存Enemyを参照せずに済むimmutable表示値へコピーする。"""

    source = tuple(enemies)
    first_alive = next((enemy for enemy in source if bool(enemy.alive)), None)
    return tuple(
        EnemyView(
            key=str(enemy.key),
            name=str(enemy.name_ja),
            hp=int(enemy.hp),
            alive=bool(enemy.alive),
            auto_target=enemy is first_alive,
            hp_max=int(enemy.hp_max),
        )
        for enemy in source
    )


def build_map_view(game_map: Any) -> MapView:
    """現在地と隣接出口だけをGameMapから読み取ってコピーする。"""

    here = game_map.here()
    exits = tuple(
        MapExitView(
            direction=str(direction),
            destination=str(destination),
            label=str(game_map.locations[destination].name),
        )
        for direction, destination in here.exits.items()
    )
    return MapView(current_location=str(here.id), current_label=str(here.name), exits=exits)
