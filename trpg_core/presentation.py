"""UIに依存しない、読み取り専用の表示モデル。

``RenderSnapshot`` は画面を組み立てるための一時的な値であり、
``GameState.snapshot()`` とは別物である。save、replay、fixture、GameStateの
復元には使用せず、端末サイズ・ANSI・入力装置などのUI固有状態も保持しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .rules import modifier


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "actions", tuple(self.actions))
        object.__setattr__(self, "enemies", tuple(self.enemies))
        object.__setattr__(self, "recent_messages", tuple(self.recent_messages))


def build_render_snapshot(state: Any, context: PresentationContext | None = None) -> RenderSnapshot:
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
    )
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
