"""世界内対象の安定IDと、注目対象を表す副作用のない最小モデル。"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field

from .map import GameMap


_ID_SEPARATOR = ":"


def _require_exact_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field_name} must not have surrounding whitespace")
    return value


@dataclass(frozen=True)
class WorldObjectId:
    """表示名やUI上の位置に依存しない、scenario内の世界対象ID。"""

    scenario_id: str
    local_id: str

    def __post_init__(self) -> None:
        scenario_id = _require_exact_text(self.scenario_id, "scenario_id")
        local_id = _require_exact_text(self.local_id, "local_id")
        if _ID_SEPARATOR in scenario_id:
            raise ValueError("scenario_id must not contain ':'")
        if local_id.startswith("/") or local_id.endswith("/") or "//" in local_id:
            raise ValueError("local_id must contain only non-empty path segments")


def serialize_world_object_id(object_id: WorldObjectId) -> str:
    """WorldObjectIdをfixture接頭辞を含まない明示文字列へ変換する。"""

    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    return f"{object_id.scenario_id}{_ID_SEPARATOR}{object_id.local_id}"


def parse_world_object_id(value: str) -> WorldObjectId:
    """最初の区切りで明示文字列を分割し、WorldObjectIdを返す。"""

    text = _require_exact_text(value, "value")
    if _ID_SEPARATOR not in text:
        raise ValueError("world object ID must contain ':'")
    scenario_id, local_id = text.split(_ID_SEPARATOR, 1)
    return WorldObjectId(scenario_id=scenario_id, local_id=local_id)


@dataclass(frozen=True)
class WorldObjectSpec:
    """世界対象の静的でUI非依存な最小定義。"""

    object_id: WorldObjectId
    kind: str
    label: str
    scene_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, WorldObjectId):
            raise ValueError("object_id must be a WorldObjectId")
        _require_exact_text(self.kind, "kind")
        _require_exact_text(self.label, "label")
        if self.scene_id is not None and not isinstance(self.scene_id, str):
            raise ValueError("scene_id must be a string or None")


@dataclass(frozen=True)
class WorldObjectVisibility:
    """Scene内の存在、認識、focus可否を独立して表す。"""

    exists_in_scene: bool
    perceived: bool
    focus_candidate: bool

    def __post_init__(self) -> None:
        for field_name in ("exists_in_scene", "perceived", "focus_candidate"):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"{field_name} must be a bool")
        if self.perceived and not self.exists_in_scene:
            raise ValueError("perceived object must exist in the scene")
        if self.focus_candidate and not self.perceived:
            raise ValueError("focus candidate must be perceived")


@dataclass(frozen=True)
class WorldFact:
    """表示文章やLOD条件を含まない、安定key付きの最小fact。"""

    key: str
    value: str

    def __post_init__(self) -> None:
        _require_exact_text(self.key, "fact key")
        if not isinstance(self.value, str):
            raise ValueError("fact value must be a string")


@dataclass(frozen=True)
class VisibleWorldObjectFacts:
    """Domain外へ渡してよいfactだけのprojection。"""

    facts: tuple[WorldFact, ...] = ()

    def __post_init__(self) -> None:
        facts = tuple(self.facts)
        _validate_fact_keys(facts)
        object.__setattr__(self, "facts", facts)


@dataclass(frozen=True)
class WorldObjectFactPartition:
    """Domain内部でのみ扱うvisible/hiddenの完全partition。"""

    visible: tuple[WorldFact, ...]
    hidden: tuple[WorldFact, ...]

    def __post_init__(self) -> None:
        visible = tuple(self.visible)
        hidden = tuple(self.hidden)
        _validate_fact_keys(visible + hidden)
        object.__setattr__(self, "visible", visible)
        object.__setattr__(self, "hidden", hidden)


@dataclass(frozen=True)
class SceneWorldObject:
    """権威specとvisibility、公開可能factを結ぶscene query結果。"""

    spec: WorldObjectSpec
    visibility: WorldObjectVisibility
    visible_facts: VisibleWorldObjectFacts = field(default_factory=VisibleWorldObjectFacts)

    def __post_init__(self) -> None:
        if not isinstance(self.spec, WorldObjectSpec):
            raise ValueError("spec must be a WorldObjectSpec")
        if not isinstance(self.visibility, WorldObjectVisibility):
            raise ValueError("visibility must be a WorldObjectVisibility")
        if not isinstance(self.visible_facts, VisibleWorldObjectFacts):
            raise ValueError("visible_facts must be VisibleWorldObjectFacts")


def _validate_fact_keys(facts: Sequence[WorldFact]) -> frozenset[str]:
    keys: set[str] = set()
    for fact in facts:
        if not isinstance(fact, WorldFact):
            raise ValueError("facts must contain only WorldFact values")
        if fact.key in keys:
            raise ValueError(f"duplicate fact key: {fact.key}")
        keys.add(fact.key)
    return frozenset(keys)


def partition_world_object_facts(
    facts: Sequence[WorldFact],
    *,
    visible_fact_keys: Collection[str],
) -> WorldObjectFactPartition:
    """Authoritative factsを入力順のままvisible/hiddenへ分割する。"""

    source = tuple(facts)
    fact_keys = _validate_fact_keys(source)
    visible_keys = tuple(visible_fact_keys)
    if any(not isinstance(key, str) or not key for key in visible_keys):
        raise ValueError("visible fact keys must be non-empty strings")
    if len(set(visible_keys)) != len(visible_keys):
        raise ValueError("duplicate visible fact key")
    unknown = set(visible_keys) - fact_keys
    if unknown:
        raise ValueError(f"unknown visible fact key: {sorted(unknown)[0]}")
    selected = frozenset(visible_keys)
    return WorldObjectFactPartition(
        visible=tuple(fact for fact in source if fact.key in selected),
        hidden=tuple(fact for fact in source if fact.key not in selected),
    )


def validate_world_object_specs(
    specs: Iterable[WorldObjectSpec],
) -> tuple[WorldObjectSpec, ...]:
    """入力順を保ってtupleへコピーし、重複object IDを拒否する。"""

    result = tuple(specs)
    seen: set[WorldObjectId] = set()
    for spec in result:
        if not isinstance(spec, WorldObjectSpec):
            raise ValueError("specs must contain only WorldObjectSpec values")
        if spec.object_id in seen:
            raise ValueError(
                f"duplicate world object ID: {serialize_world_object_id(spec.object_id)}"
            )
        seen.add(spec.object_id)
    return result


def location_world_object_id(
    scenario_id: str,
    location_id: str,
) -> WorldObjectId:
    """map location IDをlocation名前空間の安定した世界対象IDへ変換する。"""

    location = _require_exact_text(location_id, "location_id")
    return WorldObjectId(
        scenario_id=scenario_id,
        local_id=f"location/{location}",
    )


def build_map_location_world_object_specs(
    scenario_id: str,
    game_map: GameMap,
) -> tuple[WorldObjectSpec, ...]:
    """GameMap内の全locationをID順で静的WorldObjectSpecへコピーする。"""

    specs = (
        WorldObjectSpec(
            object_id=location_world_object_id(scenario_id, location_id),
            kind="location",
            label=game_map.locations[location_id].name,
            scene_id=location_id,
        )
        for location_id in sorted(game_map.locations)
    )
    return validate_world_object_specs(specs)


def validate_scene_world_objects(
    objects: Iterable[SceneWorldObject],
    *,
    scenario_id: str,
) -> tuple[SceneWorldObject, ...]:
    """Scene query結果をtuple化し、型・scenario・ID一意性を検証する。"""

    WorldObjectId(scenario_id=scenario_id, local_id="scene-validation")
    result = tuple(objects)
    seen: set[WorldObjectId] = set()
    for item in result:
        if not isinstance(item, SceneWorldObject):
            raise ValueError("scene objects must contain only SceneWorldObject values")
        object_id = item.spec.object_id
        if object_id.scenario_id != scenario_id:
            raise ValueError("scene object belongs to another scenario")
        if object_id in seen:
            raise ValueError(
                f"duplicate world object ID: {serialize_world_object_id(object_id)}"
            )
        seen.add(object_id)
    return result


def world_objects_for_current_scene(
    *,
    scenario_id: str,
    game_map: GameMap | None,
) -> tuple[SceneWorldObject, ...]:
    """現在locationに属する認識済みobjectを返す単一の権威query。"""

    WorldObjectId(scenario_id=scenario_id, local_id="scene-validation")
    if game_map is None:
        return ()
    if game_map.current not in game_map.locations:
        raise ValueError("game_map.current must identify an existing location")
    specs = build_map_location_world_object_specs(scenario_id, game_map)
    visibility = WorldObjectVisibility(
        exists_in_scene=True, perceived=True, focus_candidate=True,
    )
    return validate_scene_world_objects(
        (
            SceneWorldObject(spec=spec, visibility=visibility)
            for spec in specs
            if spec.scene_id == game_map.current
        ),
        scenario_id=scenario_id,
    )


def focusable_world_object_ids(
    scene_objects: Iterable[SceneWorldObject],
    *,
    scenario_id: str,
) -> tuple[WorldObjectId, ...]:
    """権威scene結果から現在focus可能なIDだけを安定順で抽出する。"""

    validated = validate_scene_world_objects(scene_objects, scenario_id=scenario_id)
    result = (
        item.spec.object_id
        for item in validated
        if item.visibility.exists_in_scene
        and item.visibility.perceived
        and item.visibility.focus_candidate
    )
    return tuple(sorted(result, key=serialize_world_object_id))


def focusable_world_object_ids_for_current_location(
    scenario_id: str,
    game_map: GameMap,
    specs: Iterable[WorldObjectSpec] | None = None,
) -> tuple[WorldObjectId, ...]:
    """後方互換のlocation query。候補抽出はscene境界へ委譲する。"""

    if game_map.current not in game_map.locations:
        raise ValueError("game_map.current must identify an existing location")
    if specs is None:
        scene_objects = world_objects_for_current_scene(
            scenario_id=scenario_id, game_map=game_map,
        )
    else:
        validated = validate_world_object_specs(specs)
        visibility = WorldObjectVisibility(True, True, True)
        scene_objects = validate_scene_world_objects(
            (
                SceneWorldObject(spec=spec, visibility=visibility)
                for spec in validated
                if spec.object_id.scenario_id == scenario_id
                and spec.scene_id == game_map.current
            ),
            scenario_id=scenario_id,
        )
    return focusable_world_object_ids(scene_objects, scenario_id=scenario_id)


@dataclass(frozen=True)
class FocusState:
    """engineが確定した現在の注目対象だけを保持する。"""

    focused_object_id: WorldObjectId | None = None

    def __post_init__(self) -> None:
        if (self.focused_object_id is not None
                and not isinstance(self.focused_object_id, WorldObjectId)):
            raise ValueError("focused_object_id must be a WorldObjectId or None")


def set_focus(
    state: FocusState,
    object_id: WorldObjectId,
    *,
    focusable_object_ids: Collection[WorldObjectId],
) -> FocusState:
    """権威集合に含まれる対象だけへ、副作用なしでfocusを設定する。"""

    if not isinstance(state, FocusState):
        raise ValueError("state must be a FocusState")
    if not isinstance(object_id, WorldObjectId):
        raise ValueError("object_id must be a WorldObjectId")
    if object_id not in focusable_object_ids:
        raise ValueError("object_id is not currently focusable")
    if state.focused_object_id == object_id:
        return state
    return FocusState(focused_object_id=object_id)


def clear_focus(state: FocusState) -> FocusState:
    """副作用なしでfocusを解除する。未設定なら元の値を返す。"""

    if not isinstance(state, FocusState):
        raise ValueError("state must be a FocusState")
    if state.focused_object_id is None:
        return state
    return FocusState()
