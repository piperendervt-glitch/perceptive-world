"""世界内対象の安定IDと、注目対象を表す副作用のない最小モデル。"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass

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


def focusable_world_object_ids_for_current_location(
    scenario_id: str,
    game_map: GameMap,
    specs: Iterable[WorldObjectSpec],
) -> tuple[WorldObjectId, ...]:
    """現在map locationとscenarioに属する静的focus候補IDを返す。"""

    if game_map.current not in game_map.locations:
        raise ValueError("game_map.current must identify an existing location")
    WorldObjectId(scenario_id=scenario_id, local_id="scene-validation")
    validated = validate_world_object_specs(specs)
    matching = (
        spec.object_id
        for spec in validated
        if spec.object_id.scenario_id == scenario_id
        and spec.scene_id == game_map.current
    )
    return tuple(sorted(matching, key=serialize_world_object_id))


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
