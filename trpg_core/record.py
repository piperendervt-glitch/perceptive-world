"""record.py — セッションを「シナリオ+入力列+ログ」のフィクスチャに録画する.

用途:
  1. 型付き入力ファイルから録画:
       python -m trpg_core.record --scenario goblin --seed 7 --inputs in.txt --out fx.json
     （in.txt は 1 行 1 入力。explore:elder / choice:藪を抜ける / combat:attack ...）
  2. 対話プレイを録画:
       python -m trpg_core.record --scenario goblin --seed 7 --play --out fx.json
     （実際に遊んだ入力と結果ログをそのままフィクスチャ化）

録画したフィクスチャは trpg_core.replay で再生・検証できる（決定論なので完全一致するはず）。
LLM は一切呼ばない。

Step 3（GM を LLM 化）で、ここで録ったフィクスチャを replay(mode="state") にかければ、
描写が変わってもゲーム状態イベントが不変であることを検証できる（replay.py 参照）。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys

from .input_actions import (
    ApplyLodUnlockAction, ClearFocusAction, DepartAction, ExploreAction,
    InspectFocusedObjectAction, MoveToLocationAction, ObserveFocusedObjectAction,
    MovePlayerToPositionAction, SetFocusAction,
)

from .replay import (
    FixtureController, lod_runtime_trace_entry, position_trace_entry,
    serialize_lod_trace, serialize_position_trace,
)
from .record_codec import (
    CURRENT_RECORD_FORMAT_VERSION,
    serialize_record_token,
)
from .world import serialize_world_object_id

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "tests", "fixtures")


def _run_with_traces(state, controller):
    from .session import run_session
    focus_trace = []
    lod_trace = []
    position_trace = []

    def observe(action, authoritative_focus):
        if isinstance(action, (SetFocusAction, ClearFocusAction)):
            focus_trace.append(
                None if authoritative_focus is None
                else serialize_world_object_id(authoritative_focus)
            )
        lod_trace.append(lod_runtime_trace_entry(state.lod_runtime))
        position_trace.append(position_trace_entry(state.player_position))

    result = run_session(state, controller, on_village_event_applied=observe)
    return (result, focus_trace, serialize_lod_trace(lod_trace),
            serialize_position_trace(position_trace))


class RecordingController:
    """任意の base コントローラをラップし、供給された入力を型付きで記録する。

    run_session が pull した入力（探索 key / 選択 / 戦闘コマンド）をそのまま録る。
    choice は表示ラベルではなく canonical key で記録する。
    """

    def __init__(self, base, scenario):
        self.base = base
        self.scenario = scenario
        self.inputs: list[str] = []
        self._pending_village_token: str | None = None

    def explores(self):
        keys = list(self.base.explores())
        self.inputs.extend(serialize_record_token("explore", k) for k in keys)
        return keys

    def begin_village(self):
        if hasattr(self.base, "begin_village"):
            self.base.begin_village()

    def village_action(self, context, **display):
        event = self.base.village_action(context, **display)
        if isinstance(event, MoveToLocationAction):
            token = serialize_record_token(
                "move-to", serialize_world_object_id(event.destination_object_id))
        elif isinstance(event, MovePlayerToPositionAction):
            token = serialize_record_token(
                "move-player-to", f"{event.destination.x},{event.destination.y}",
            )
        elif isinstance(event, SetFocusAction):
            token = serialize_record_token(
                "focus:set", serialize_world_object_id(event.object_id))
        elif isinstance(event, ClearFocusAction):
            token = serialize_record_token("focus:clear")
        elif isinstance(event, ObserveFocusedObjectAction):
            token = serialize_record_token("observe")
        elif isinstance(event, InspectFocusedObjectAction):
            token = serialize_record_token("inspect")
        elif isinstance(event, ApplyLodUnlockAction):
            token = serialize_record_token(
                "lod-unlock",
                f"{serialize_world_object_id(event.object_id)}:{event.target_cap}",
            )
        elif isinstance(event, ExploreAction):
            token = serialize_record_token("explore", event.key)
        elif isinstance(event, DepartAction):
            token = serialize_record_token("depart")
        else:
            return event
        if self._pending_village_token is not None:
            raise RuntimeError("previous village event has not been applied")
        self._pending_village_token = token
        return event

    def village_event_applied(self, event) -> None:
        if self._pending_village_token is None:
            return
        self.inputs.append(self._pending_village_token)
        self._pending_village_token = None

    def village_event_rejected(self, event, error) -> None:
        self._pending_village_token = None
        if hasattr(self.base, "announce"):
            self.base.announce(str(error))

    def choice(self, node, options):
        key = self.base.choice(node, options)
        self.inputs.append(serialize_record_token("choice", key))
        return key

    def combat_command(self, state, enemies):
        cmd = self.base.combat_command(state, enemies)
        self.inputs.append(serialize_record_token("combat", cmd))
        return cmd


def _new_state(scenario_id: str, seed: int, respawn: bool):
    from .session import GameState
    from .scenario_loader import load_scenario
    state = GameState(seed, scenario=load_scenario(scenario_id))
    state.respawn_on_defeat = respawn
    return state


def build_fixture(scenario_id: str, seed: int, base_controller, respawn=False) -> dict:
    """base_controller でセッションを走らせ、入力列と結果ログを録ってフィクスチャ化する。"""
    state = _new_state(scenario_id, seed, respawn)
    rec = RecordingController(base_controller, state.scenario)
    _result, focus_trace, lod_trace, position_trace = _run_with_traces(state, rec)
    fixture = {"format_version": CURRENT_RECORD_FORMAT_VERSION,
               "scenario": scenario_id, "seed": seed, "inputs": rec.inputs,
               "expected_log": state.log,
               "expected_focus_trace": focus_trace,
               "expected_lod_trace": lod_trace,
               "expected_position_trace": position_trace}
    if respawn:
        fixture["respawn"] = True
    return fixture


def fixture_from_inputs(
    scenario_id: str, seed: int, inputs, respawn=False, *, input_format_version=0,
) -> dict:
    """既にある型付き入力列からフィクスチャを生成（expected_log を再生成）。"""
    state = _new_state(scenario_id, seed, respawn)
    controller = FixtureController(
        inputs, state.scenario, format_version=input_format_version,
    )
    controller.well_effect_profile = "current"
    controller.village_effect_profile = "all_current"
    _result, focus_trace, lod_trace, position_trace = _run_with_traces(state, controller)
    controller.assert_all_events_consumed()
    fixture = {"format_version": CURRENT_RECORD_FORMAT_VERSION,
               "scenario": scenario_id, "seed": seed,
               "inputs": controller.canonical_inputs,
               "expected_log": state.log,
               "expected_focus_trace": focus_trace,
               "expected_lod_trace": lod_trace,
               "expected_position_trace": position_trace}
    if respawn:
        fixture["respawn"] = True
    return fixture


def save_fixture(fixture: dict, path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fixture, f, ensure_ascii=False, indent=1)
    return path


def _record_interactive(scenario_id: str, seed: int, ui_mode: str = "menu") -> dict:
    """対話プレイを録画する（ConsoleController をラップ）。"""
    from .session import GameState, ConsoleController, run_session, LOG_DIR
    from .scenario_loader import load_scenario
    scenario = load_scenario(scenario_id)
    state = GameState(seed, scenario=scenario)
    state.respawn_on_defeat = True
    console = ConsoleController(state, os.path.join(LOG_DIR, "saves"), ui_mode=ui_mode)
    rec = RecordingController(console, scenario)
    print("=" * 60)
    print(f"  録画モード — {scenario.title}（seed={seed}）")
    print("=" * 60)
    if scenario.intro:
        print(scenario.intro)
    result, focus_trace, lod_trace, position_trace = _run_with_traces(state, rec)
    print()
    print(scenario.ending_text(result))
    print(f"\n>>> 結果: {result}")
    fixture = {"format_version": CURRENT_RECORD_FORMAT_VERSION,
               "scenario": scenario_id, "seed": seed, "inputs": rec.inputs,
               "expected_log": state.log,
               "expected_focus_trace": focus_trace,
               "expected_lod_trace": lod_trace,
               "expected_position_trace": position_trace}
    if state.respawn_on_defeat:
        # respawn が実際に起きたかは inputs/ログから判断できるが、既定 True で保存しても
        # 再生時に defeat しなければ無影響。明示のため付けておく。
        fixture["respawn"] = True
    return fixture


def main(argv):
    ap = argparse.ArgumentParser(description="セッションをフィクスチャに録画する（LLM 不使用）。")
    ap.add_argument("--scenario", default="goblin")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--inputs", help="型付き入力ファイル（1 行 1 入力）。省略時は --play")
    ap.add_argument("--play", action="store_true", help="対話プレイを録画する")
    ap.add_argument("--ui", choices=("menu", "tui"), default="menu",
                    help="対話録画のUI（既定: menu）")
    ap.add_argument("--out", help="出力パス（省略時は tests/fixtures/<scenario>_seed<seed>.json）")
    args = ap.parse_args(argv)

    out = args.out or os.path.join(FIXTURE_DIR, f"{args.scenario}_seed{args.seed}.json")

    if args.play or not args.inputs:
        fixture = _record_interactive(args.scenario, args.seed, ui_mode=args.ui)
    else:
        with open(args.inputs, "r", encoding="utf-8") as f:
            inputs = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
        fixture = fixture_from_inputs(args.scenario, args.seed, inputs)

    path = save_fixture(fixture, out)
    print(f"録画 → {path}（scenario={fixture['scenario']} seed={fixture['seed']}, "
          f"{len(fixture['inputs'])} inputs, {len(fixture['expected_log'])} events）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
