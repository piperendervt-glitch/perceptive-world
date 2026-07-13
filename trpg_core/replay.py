"""replay.py — フィクスチャ（シナリオ+入力列+ログ）の再生・検証（★汎用回帰フレーム）.

フィクスチャ形式（tests/fixtures/*.json）:
    {
      "scenario": "goblin",
      "seed": 7,
      "inputs": ["explore:elder", "choice:藪を抜ける【…】", "combat:attack", ...],
      "expected_log": [ ...イベント... ]
    }

scenario + seed + inputs があれば expected_log は決定論的に再生成できる（乱数はコード独占）。
このモジュールは inputs を消費する FixtureController でセッションを再実行し、結果ログを
expected_log と比較する。LLM は一切呼ばない。

────────────────────────────────────────────────────────────────────────
Step 3（GM を LLM に置き換える）への布石:
  - Step 3 で描写を LLM 生成にしたとき、**同じフィクスチャを replay** し、
    **ゲーム状態イベント（check / player_attack / enemy_attack / ending 等）が一致**すれば、
    描写が変わってもゲームは不変であることを保証できる。
  - そのため本フレームは各イベントを「ゲーム状態イベント / 描写イベント」に分類できる
    （is_game_state / is_narration）。**描写だけ比較から外す** replay(mode="state") を用意する。
  - 分類は「型による」判定にしてある（ログの各イベントに余分なフィールドを足さない＝
    既存 55 events を一切変えないため）。Step 3 で GM 描写を載せるときは type="narration"
    のイベントとして足せば、mode="state" が自動的にそれを除外する。
────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import os
from collections import deque

from .input_actions import (
    ApplyLodUnlockAction, ClearFocusAction, DepartAction, ExploreAction,
    InspectFocusedObjectAction, MoveToLocationAction, ObserveFocusedObjectAction,
    MovePlayerToPositionAction, SetFocusAction,
    StoryChoiceAction,
)
from .spatial import PlayerPosition
from .lod import derive_current_lod
from .lod_actions import LodRuntimeState
from .lod_content import lod_content_for_world_object

from .record_codec import (
    parse_record_token,
    record_format_version,
    serialize_record_token,
)
from .world import parse_world_object_id, serialize_world_object_id

# --- イベント分類（型で判定。ログ本体は書き換えない）-----------------------
# 描写イベント: Step 3 で GM(LLM) が生成する自由記述の型。今は未使用（描写は presenter 側）。
NARRATION_EVENT_TYPES = frozenset({"narration", "describe"})

# ゲーム進行の核（判定・数値・進行）。描写が変わっても必ず一致すべき不変集合。
PROGRESSION_EVENT_TYPES = frozenset({
    "check", "player_attack", "enemy_attack", "mp_cost",
    "herb", "combat_win", "defeat", "respawn", "ending",
})


def is_narration(ev: dict) -> bool:
    """描写イベントか（Step 3 で LLM 描写を比較から外すための判定）。"""
    return ev.get("type") in NARRATION_EVENT_TYPES


def is_game_state(ev: dict) -> bool:
    """ゲーム状態イベントか（描写以外すべて）。"""
    return not is_narration(ev)


def game_state_events(log: list[dict]) -> list[dict]:
    """描写イベントを除いたログ（Step 3 の『描写除外』比較に使う）。"""
    return [e for e in log if is_game_state(e)]


def progression_events(log: list[dict]) -> list[dict]:
    """判定・数値・進行の核イベントだけ抜き出す（最も強い不変）。"""
    return [e for e in log if e.get("type") in PROGRESSION_EVENT_TYPES]


# --- 入力列を消費するコントローラ（run_session と接続）-----------------------

class FixtureController:
    """型付き入力列（explore:/choice:/combat:）を run_session に供給する。

    ScriptedController と同じインターフェース（explores/choice/combat_command）。
    choice は key / 完全ラベル / ラベル部分一致 のいずれでも解決できる（人が短縮形で
    書いても replay できる）。map 移動は UI なので入力列には現れない（探索は選んだ key 列）。
    """

    def __init__(self, inputs, scenario, *, format_version=0):
        self.q = deque(inputs)
        self.sc = scenario
        self.format_version = format_version
        self.legacy_village_batch = False
        self.canonical_inputs: list[str] = []
        self.well_effect_profile = "legacy" if format_version <= 5 else "current"
        self.village_effect_profile = (
            "legacy_all" if format_version <= 5
            else ("well_current" if format_version == 6 else "all_current")
        )
        # F-3 runtime state is intentionally outside record formats through v7.
        self.trace_memory_profile = "legacy" if format_version <= 7 else "current"

    def explores(self):
        keys = []
        while self.q:
            parsed = parse_record_token(self.q[0], format_version=self.format_version)
            if parsed.verb != "explore":
                break
            self.q.popleft()
            keys.append(parsed.payload)
            self.canonical_inputs.append(serialize_record_token("explore", parsed.payload))
        return keys

    def village_action(self, context, **_display):
        if self.format_version == 0:
            if not self.q:
                return self._legacy_depart(context)
            parsed = parse_record_token(self.q[0], format_version=0)
            if parsed.verb != "explore":
                return self._legacy_depart(context)
            if context.current_location_object_id is not None:
                target = next(
                    (location_id for location_id, data in self.sc.map_locations.items()
                     if data.get("action") == parsed.payload),
                    None,
                )
                current = context.current_location_object_id.local_id[len("location/"):]
                if target is not None and target != current:
                    first = self._first_step(current, target)
                    object_id = parse_world_object_id(
                        f"{self.sc.id}:location/{first}"
                    )
                    self.canonical_inputs.append(serialize_record_token(
                        "move-to", f"{self.sc.id}:location/{first}"))
                    return MoveToLocationAction(object_id)
            self.q.popleft()
            self.canonical_inputs.append(serialize_record_token("explore", parsed.payload))
            return ExploreAction(parsed.payload)
        if not self.q:
            raise ValueError("入力列が尽きた（village event を要求）")
        item = self.q[0]
        parsed = parse_record_token(item, format_version=self.format_version)
        if parsed.verb in {"choice", "combat"}:
            raise ValueError(f"village中に不正な入力: {item!r}")
        self.q.popleft()
        if parsed.verb == "move-to":
            event = MoveToLocationAction(parse_world_object_id(parsed.payload))
        elif parsed.verb == "move-player-to":
            x, y = parsed.payload.split(",")
            event = MovePlayerToPositionAction(PlayerPosition(int(x), int(y)))
        elif parsed.verb == "focus:set":
            event = SetFocusAction(parse_world_object_id(parsed.payload))
        elif parsed.verb == "focus:clear":
            event = ClearFocusAction()
        elif parsed.verb == "observe":
            event = ObserveFocusedObjectAction()
        elif parsed.verb == "inspect":
            event = InspectFocusedObjectAction()
        elif parsed.verb == "lod-unlock":
            object_id, target_cap = parsed.payload.rsplit(":", 1)
            event = ApplyLodUnlockAction(
                parse_world_object_id(object_id), int(target_cap),
            )
        elif parsed.verb == "explore":
            event = ExploreAction(parsed.payload)
        elif parsed.verb == "depart":
            event = DepartAction()
        else:
            raise ValueError(f"unsupported village token: {item!r}")
        self.canonical_inputs.append(item)
        return event

    def _legacy_depart(self, context):
        if context.current_location_object_id is not None and not context.can_depart:
            current = context.current_location_object_id.local_id[len("location/"):]
            target = next(
                (location_id for location_id, data in self.sc.map_locations.items()
                 if data.get("leads_to_adventure")),
                None,
            )
            if target is not None and target != current:
                first = self._first_step(current, target)
                payload = f"{self.sc.id}:location/{first}"
                self.canonical_inputs.append(serialize_record_token("move-to", payload))
                return MoveToLocationAction(parse_world_object_id(payload))
        self.canonical_inputs.append(serialize_record_token("depart"))
        return DepartAction()

    def _first_step(self, start, target):
        pending = deque([(start, None)])
        seen = {start}
        while pending:
            location, first = pending.popleft()
            for destination in self.sc.map_locations[location].get("exits", {}).values():
                if destination in seen:
                    continue
                step = destination if first is None else first
                if destination == target:
                    return step
                seen.add(destination)
                pending.append((destination, step))
        raise ValueError(f"legacy explore destination is unreachable: {target!r}")

    def choice(self, node, options):
        item = self._pop("choice")
        key = self._resolve_choice(node, item)
        self.canonical_inputs.append(serialize_record_token("choice", key))
        return key

    def story_action(self, state, node):
        if self.format_version < 5:
            return StoryChoiceAction(self.choice(node.id, [c.key for c in node.choices]))
        if not self.q:
            raise ValueError("入力列が尽きた（story action を要求）")
        item = self.q.popleft()
        parsed = parse_record_token(item, format_version=self.format_version)
        if parsed.verb == "move-player-to":
            x, y = parsed.payload.split(",")
            action = MovePlayerToPositionAction(PlayerPosition(int(x), int(y)))
        elif parsed.verb == "choice":
            action = StoryChoiceAction(self._resolve_choice(node.id, parsed.payload))
        else:
            raise ValueError(f"story中に不正な入力: {item!r}")
        self.canonical_inputs.append(item)
        return action

    def combat_command(self, state, enemies):
        command = self._pop("combat")
        self.canonical_inputs.append(serialize_record_token("combat", command))
        return command

    # --- 内部 ---
    def _pop(self, kind):
        if not self.q:
            raise ValueError(f"入力列が尽きた（{kind} を要求）")
        item = self.q.popleft()
        parsed = parse_record_token(item, format_version=self.format_version)
        if parsed.verb != kind:
            raise ValueError(f"入力の型が不一致: {kind} を要求したが '{item}'")
        return parsed.payload

    def _resolve_choice(self, node, val):
        choices = self.sc.node(node).choices
        for c in choices:                      # 1) key 完全一致
            if c.key == val:
                return c.key
        if self.format_version >= 1:
            raise ValueError(
                f"choice key '{val}' を node '{node}' で解決できない（候補: "
                f"{[c.key for c in choices]}）"
            )
        for c in choices:                      # 2) ラベル完全一致
            if c.label == val:
                return c.key
        hits = [c for c in choices if val in c.label or c.label.startswith(val)]
        if len(hits) == 1:                     # 3) ラベル部分一致（一意なら）
            return hits[0].key
        raise ValueError(
            f"choice '{val}' を node '{node}' で解決できない（候補: "
            f"{[(c.key, c.label) for c in choices]}）"
        )

    def remaining_events(self):
        return tuple(self.q)

    def assert_all_events_consumed(self):
        if self.q:
            raise ValueError(
                f"未消費の replay event: remaining={len(self.q)}, first={self.q[0]!r}"
            )


# --- 再生と比較 --------------------------------------------------------------

def _run(
    scenario_id: str, seed: int, inputs, respawn=False, *, format_version=0,
    collect_focus_trace=False, collect_lod_trace=False, collect_position_trace=False,
):
    from .session import GameState, run_session
    from .spatial_content import legacy_spatial_definition_for_scene
    from .scenario_loader import load_scenario
    provider = (
        legacy_spatial_definition_for_scene if format_version <= 3 else None
    )
    state_args = ({"spatial_definition_provider": provider}
                  if provider is not None else {})
    if format_version <= 4:
        state_args["story_spatial_definition_provider"] = lambda _scenario, _node: None
    state = GameState(seed, scenario=load_scenario(scenario_id), **state_args)
    state.respawn_on_defeat = respawn
    controller = FixtureController(inputs, state.scenario, format_version=format_version)
    focus_trace = [] if collect_focus_trace else None
    lod_trace = [] if collect_lod_trace else None
    position_trace = [] if collect_position_trace else None

    def observe(action, authoritative_focus):
        if focus_trace is not None and isinstance(action, (SetFocusAction, ClearFocusAction)):
            focus_trace.append(authoritative_focus)
        if lod_trace is not None:
            lod_trace.append(lod_runtime_trace_entry(state.lod_runtime))
        if position_trace is not None:
            position_trace.append(position_trace_entry(state.player_position))

    run_session(
        state, controller,
        on_village_event_applied=(
            observe if (focus_trace is not None or lod_trace is not None
                        or position_trace is not None) else None
        ),
    )
    controller.assert_all_events_consumed()
    return state, focus_trace, lod_trace, position_trace


def expected_focus_trace(fixture: dict, *, format_version: int):
    if "expected_focus_trace" not in fixture:
        return None
    if format_version not in {1, 2, 3, 4, 5, 6, 7}:
        raise ValueError("expected_focus_trace is supported only for format_version 1 through 7")
    raw = fixture["expected_focus_trace"]
    if not isinstance(raw, list):
        raise ValueError("expected_focus_trace must be an array")
    parsed = []
    for index, value in enumerate(raw):
        if value is None:
            parsed.append(None)
        elif type(value) is str:
            parsed.append(parse_world_object_id(value))
        else:
            raise ValueError(
                f"expected_focus_trace[{index}] must be a WorldObjectId string or null"
            )
    return tuple(parsed)


def _focus_value(value):
    return "null" if value is None else serialize_world_object_id(value)


def assert_focus_trace_matches(expected, actual):
    actual = tuple(actual)
    if tuple(expected) == actual:
        return
    limit = min(len(expected), len(actual))
    index = next((i for i in range(limit) if expected[i] != actual[i]), limit)
    missing = object()
    expected_value = expected[index] if index < len(expected) else missing
    actual_value = actual[index] if index < len(actual) else missing
    display_expected = "<missing>" if expected_value is missing else _focus_value(expected_value)
    display_actual = "<missing>" if actual_value is missing else _focus_value(actual_value)
    raise ValueError(
        "expected_focus_trace mismatch: "
        f"expected_count={len(expected)}, actual_count={len(actual)}, index={index}, "
        f"expected={display_expected}, actual={display_actual}"
    )


def lod_runtime_trace_entry(runtime: LodRuntimeState) -> tuple[tuple[str, int, int, int], ...]:
    """Return one stable, derived LOD runtime snapshot for a canonical event."""
    values = []
    for progress in runtime.objects:
        content = lod_content_for_world_object(progress.object_id)
        if content is None:
            raise ValueError("LOD runtime object has no content")
        values.append((
            serialize_world_object_id(progress.object_id),
            progress.attention.attention_level,
            progress.lod_state.unlocked_lod_cap,
            derive_current_lod(content.lod_spec, progress.attention, progress.lod_state),
        ))
    return tuple(values)


def serialize_lod_trace(trace) -> list[list[dict]]:
    return [[{
        "object_id": object_id,
        "attention_level": attention,
        "unlocked_lod_cap": cap,
        "current_lod": current,
    } for object_id, attention, cap, current in entry] for entry in trace]


def expected_lod_trace(fixture: dict, *, format_version: int):
    if "expected_lod_trace" not in fixture:
        return None
    if format_version not in {2, 3, 4, 5, 6, 7}:
        raise ValueError("expected_lod_trace is supported only for format_version 2 through 7")
    raw = fixture["expected_lod_trace"]
    if not isinstance(raw, list):
        raise ValueError("expected_lod_trace must be an array")
    parsed = []
    keys = {"object_id", "attention_level", "unlocked_lod_cap", "current_lod"}
    for event_index, entry in enumerate(raw):
        if not isinstance(entry, list):
            raise ValueError(f"expected_lod_trace[{event_index}] must be an array")
        event = []
        seen = set()
        for object_index, value in enumerate(entry):
            if not isinstance(value, dict) or set(value) != keys:
                raise ValueError("expected_lod_trace object must have exact fields")
            object_id = value["object_id"]
            parsed_id = parse_world_object_id(object_id) if type(object_id) is str else None
            if parsed_id is None or serialize_world_object_id(parsed_id) != object_id:
                raise ValueError("expected_lod_trace object_id must be canonical")
            numbers = tuple(value[key] for key in (
                "attention_level", "unlocked_lod_cap", "current_lod",
            ))
            if any(type(number) is not int or number < 0 for number in numbers):
                raise ValueError("expected_lod_trace numeric fields must be non-negative ints")
            if object_id in seen:
                raise ValueError("expected_lod_trace objects must not contain duplicates")
            seen.add(object_id)
            event.append((object_id, *numbers))
        parsed.append(tuple(event))
    return tuple(parsed)


def assert_lod_trace_matches(expected, actual):
    if tuple(expected) != tuple(actual):
        raise ValueError(
            "expected_lod_trace mismatch: "
            f"expected_count={len(expected)}, actual_count={len(actual)}"
        )


def position_trace_entry(position: PlayerPosition | None):
    if position is None:
        return None
    if type(position) is not PlayerPosition:
        raise ValueError("position trace requires PlayerPosition or None")
    return (position.x, position.y)


def serialize_position_trace(trace):
    return [None if entry is None else {"x": entry[0], "y": entry[1]} for entry in trace]


def expected_position_trace(fixture: dict, *, format_version: int):
    if "expected_position_trace" not in fixture:
        return None
    if format_version not in {3, 4, 5, 6, 7}:
        raise ValueError("expected_position_trace is supported only for format_version 3 through 7")
    raw = fixture["expected_position_trace"]
    if type(raw) is not list:
        raise ValueError("expected_position_trace must be an array")
    result = []
    for index, value in enumerate(raw):
        if value is None:
            result.append(None)
        elif type(value) is dict and set(value) == {"x", "y"}:
            if type(value["x"]) is not int or type(value["y"]) is not int:
                raise ValueError(f"expected_position_trace[{index}] coordinates must be ints")
            result.append((value["x"], value["y"]))
        else:
            raise ValueError(f"expected_position_trace[{index}] must be x/y or null")
    return tuple(result)


def assert_position_trace_matches(expected, actual):
    if tuple(expected) != tuple(actual):
        raise ValueError(
            "expected_position_trace mismatch: "
            f"expected_count={len(expected)}, actual_count={len(actual)}"
        )


def compare_logs(expected: list, actual: list):
    """完全一致なら None。違えば (index, expected_event, actual_event) を返す。"""
    n = min(len(expected), len(actual))
    for i in range(n):
        if expected[i] != actual[i]:
            return (i, expected[i], actual[i])
    if len(expected) != len(actual):
        return (n,
                expected[n] if n < len(expected) else None,
                actual[n] if n < len(actual) else None)
    return None


def replay_fixture(fixture: dict, mode: str = "full"):
    """フィクスチャを再生し比較する。

    mode="full"  : 全イベントを比較（M2 の回帰＝完全一致）。
    mode="state" : 描写イベントを除いて比較（Step 3 で描写だけ変わる場合の検証）。
    戻り値: (ok: bool, actual_log: list, diff: tuple|None)
    """
    version = record_format_version(fixture)
    expected_trace = expected_focus_trace(fixture, format_version=version)
    expected_lod = expected_lod_trace(fixture, format_version=version)
    expected_position = expected_position_trace(fixture, format_version=version)
    state, actual_trace, actual_lod, actual_position = _run(
        fixture["scenario"], fixture["seed"], fixture["inputs"],
        respawn=bool(fixture.get("respawn", False)), format_version=version,
        collect_focus_trace=expected_trace is not None,
        collect_lod_trace=expected_lod is not None,
        collect_position_trace=expected_position is not None,
    )
    actual = state.log
    expected = fixture["expected_log"]
    if mode == "state":
        expected = game_state_events(expected)
        actual = game_state_events(actual)
    diff = compare_logs(expected, actual)
    if diff is None and expected_trace is not None:
        assert_focus_trace_matches(expected_trace, actual_trace)
    if diff is None and expected_lod is not None:
        assert_lod_trace_matches(expected_lod, actual_lod)
    if diff is None and expected_position is not None:
        assert_position_trace_matches(expected_position, actual_position)
    return (diff is None, state.log, diff)


def load_fixture(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_fixture(data) -> bool:
    """新形式フィクスチャ（dict + expected_log）かどうか。旧 session_7.json（list）は除外。"""
    return isinstance(data, dict) and "expected_log" in data and "inputs" in data


def format_diff(diff) -> str:
    i, exp, act = diff
    return (f"最初の不一致 @ index {i}\n"
            f"  expected: {json.dumps(exp, ensure_ascii=False)}\n"
            f"  actual  : {json.dumps(act, ensure_ascii=False)}")


def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="フィクスチャを再生して回帰検証する（LLM 不使用）。")
    ap.add_argument("fixture", help="tests/fixtures/*.json のパス")
    ap.add_argument("--mode", choices=("full", "state"), default="full",
                    help="full=全イベント一致 / state=描写除外（Step 3 用）")
    args = ap.parse_args(argv)

    fx = load_fixture(args.fixture)
    if not is_fixture(fx):
        print(f"[SKIP] {args.fixture} はフィクスチャ形式ではない")
        return 2
    ok, actual, diff = replay_fixture(fx, mode=args.mode)
    name = os.path.basename(args.fixture)
    if ok:
        print(f"[PASS] {name}  scenario={fx['scenario']} seed={fx['seed']} "
              f"（{len(actual)} events / mode={args.mode}）")
        return 0
    print(f"[FAIL] {name}  scenario={fx['scenario']} seed={fx['seed']}")
    print(format_diff(diff))
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
