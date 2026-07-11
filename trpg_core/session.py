"""session.py — セッションループ（コンソール）＋ 決定論フロー.

自由度 0。プレイヤーは用意された選択肢（番号）と戦闘コマンド（attack/magic/herb/flee）
だけを選べる。出目・修正・目標値・成否を**すべて表示**する（普通の TRPG。隠さない）。
数値は H の内心に映るもの（I-4）として提示する。

CLI:
    python -m trpg_core.session --seed 7          # 対話プレイ
    python -m trpg_core.session --seed 7 --replay # seed=7 の参照入力列を自動再生（ログ出力）

このモジュールは LLM を一切呼ばない（import もネットワーク通信もゼロ）。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import deque
from collections.abc import Collection

from .combat import run_combat
from .input_actions import (
    DirectCommand,
    MetaRequest,
    SelectMenuIndex,
    parse_raw_input,
    resolve_combat_command,
    resolve_direction,
    resolve_menu_index,
)
from .rng import Rng
from .rules import MP_COST, modifier, roll, has_recon
from .scenario_loader import load_scenario
from .world import (
    FocusState,
    WorldObjectId,
    clear_focus as resolve_clear_focus,
    set_focus as resolve_set_focus,
)

# Windows console default cp932 chokes on CJK output; force UTF-8（resolve.py と同流儀）。
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
RELOAD = "__reload__"
DEFAULT_SCENARIO = "goblin"

# 村の地図移動の方角エイリアス（英語/略/日本語）。地図移動は乱数を消費しない（UI のみ）。
_DIR_ALIAS = {
    "north": "north", "n": "north", "北": "north", "up": "north",
    "south": "south", "s": "south", "南": "south", "down": "south",
    "east": "east", "e": "east", "東": "east", "right": "east",
    "west": "west", "w": "west", "西": "west", "left": "west",
}
_DIR_ORDER = ("north", "east", "south", "west")
_DIR_LABEL = {"north": "北", "east": "東", "south": "南", "west": "西"}


# ---------------------------------------------------------------------------
# ゲーム状態
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self, seed: int, scenario=None):
        # シナリオ（データ）を読む。char/敵/ノードはすべてここから来る。
        if scenario is None:
            scenario = load_scenario(DEFAULT_SCENARIO)
        self.scenario = scenario
        char = scenario.character
        self.seed = seed
        self.rng = Rng(seed)
        self.hp_max = char["hp_max"]
        self.mp_max = char["mp_max"]
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.str = char["str"]
        self.mag = char["mag"]
        self.vit = char["vit"]
        # 探索で得る効果（I-4: H の内心にだけ映る）。宣言はシナリオ、適用はエンジン。
        self.effects: list[dict] = []   # 受動効果（hit_bonus/damage_bonus/recon）の宣言
        self.herbs = 0                  # 回復アイテム（item 効果を畳み込んだ数）
        self.buff_labels: list[str] = []  # 内心表示用のラベル（ログには出ない）
        # 進行
        self.turn = 0
        self.node = scenario.start_node
        # 村の現在地（地図の真実源＝GameMap の current をここに永続化。save/load 対象）。
        self.location = scenario.map_start if getattr(scenario, "has_map", False) else None
        self.started = False
        self.respawn_on_defeat = False
        self.log: list[dict] = []
        self.focus_state = FocusState()
        # 表示専用フック（対話プレイでのみ設定）。**ログには一切影響しない**——
        # scripted/policy では None のままなので回帰ログはバイト単位で不変（seed=7 保証）。
        self.presenter = None

    def emit(self, **fields) -> dict:
        entry = {"t": self.turn}
        entry.update(fields)
        self.log.append(entry)
        if self.presenter is not None:
            self.presenter(entry)   # 表示のみ。乱数もログも触らない。
        return entry

    def set_focused_object(
        self,
        object_id: WorldObjectId,
        *,
        focusable_object_ids: Collection[WorldObjectId],
    ) -> None:
        self.focus_state = resolve_set_focus(
            self.focus_state,
            object_id,
            focusable_object_ids=focusable_object_ids,
        )

    def clear_focused_object(self) -> None:
        self.focus_state = resolve_clear_focus(self.focus_state)

    def transition_node(self, node: str) -> None:
        if node == self.node:
            return
        self.node = node
        self.clear_focused_object()

    def transition_location(self, location: str | None) -> None:
        if location == self.location:
            return
        self.location = location
        self.clear_focused_object()

    def reset_for_village(self) -> None:
        """敗北後の再起（Fix3）: HP/MP を全快し、授かり・薬草をリセットする。
        探索フェーズをやり直すため、一度きりの探索ボーナスも白紙に戻す。
        seed/rng/turn/log/hp_max などの進行・再現要素は保持する。"""
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.effects = []
        self.herbs = 0
        self.buff_labels = []
        # 敗北後は村の入口（広場）から歩き直す
        self.transition_location(
            self.scenario.map_start if getattr(self.scenario, "has_map", False) else None
        )

    # --- save/load（★rng の内部状態 a を含む＝ロード後の乱数列が一致する） ---
    _SNAP_FIELDS = (
        "seed", "hp_max", "mp_max", "hp", "mp", "str", "mag", "vit",
        "effects", "herbs", "buff_labels",
        "turn", "node", "location", "started", "respawn_on_defeat",
    )

    def snapshot(self) -> dict:
        snap = {k: getattr(self, k) for k in self._SNAP_FIELDS}
        snap["scenario_id"] = self.scenario.id   # 参照用（restore は既存 scenario を使う）
        snap["rng_a"] = self.rng.state()
        return snap

    def restore(self, snap: dict) -> None:
        for k in self._SNAP_FIELDS:
            if k in snap:
                setattr(self, k, snap[k])
        self.rng.set_state(snap["rng_a"])
        self.clear_focused_object()


# ---------------------------------------------------------------------------
# コントローラ（決定の供給元）
# ---------------------------------------------------------------------------

class ScriptedController:
    """入力列を機械再生する（回帰・シミュレーション用）。自由記述なし。"""

    def __init__(self, explores, node_choices, combat_cmds):
        self._explores = list(explores)
        self._choices = deque(node_choices)   # ノード選択（遭遇順）
        self._cmds = deque(combat_cmds)        # 戦闘コマンド（全戦闘を通じた順）

    def explores(self):
        return self._explores

    def choice(self, node, options):
        return self._choices.popleft()

    def combat_command(self, state, enemies):
        return self._cmds.popleft()


class PolicyController:
    """ヘッドレス自動プレイの方針（simulate 用）。分岐は常に隠密ルートを選ぶ。"""

    def __init__(self, build):
        self._build = list(build)

    def explores(self):
        return self._build

    def choice(self, node, options):
        if node == "forest":
            return "bush"
        if node in ("sneak_ok", "sneak_fail"):
            return "cave"
        if node == "cave_hall":
            return "sneak"
        return options[0]

    def combat_command(self, state, enemies):
        # HP<=7 かつ薬草あり → herb / MP>=2 → magic / else attack
        if state.hp <= 7 and state.herbs > 0:
            return "herb"
        if state.mp >= MP_COST:
            return "magic"
        return "attack"


# ---------------------------------------------------------------------------
# セッションフロー（決定論・ノードグラフを歩く）
# ---------------------------------------------------------------------------

def _goto(state: GameState, node_id: str) -> None:
    """遷移先へ移り、enter_node を刻む（ノード進入はすべてここを通す）。"""
    state.transition_node(node_id)
    state.emit(type="enter_node", node=node_id)


def _run_village(state: GameState, controller) -> None:
    """探索フェーズ（出立前／敗北後の再起）。controller が pick を供給する。"""
    from . import village
    for key in controller.explores():
        village.explore(state, key)


def _resolve_check(state: GameState, check: dict) -> bool:
    """判定つき遷移の判定を解く。check の宣言をエンジンが解釈する。
    recon_auto: 偵察があれば振らずに自動成功。recon_bonus: 偵察があれば修正に加算。"""
    stat = check["stat"]
    target = int(check["target"])
    tag = check.get("tag", stat)
    if check.get("recon_auto") and has_recon(state):
        state.emit(type="check", tag=tag, auto=True, success=True)
        return True
    mod = modifier(getattr(state, stat))
    if check.get("recon_bonus") and has_recon(state):
        mod += int(check["recon_bonus"])
    rr = roll(state.rng, mod, target)
    state.emit(type="check", tag=tag, **rr)
    return rr["success"]


def _handle_decision(state: GameState, controller, node) -> str | None:
    """決定ノードを 1 手進める。RELOAD ならそれを返し、それ以外は None。"""
    key = controller.choice(node.id, [c.key for c in node.choices])
    if key == RELOAD:
        return RELOAD
    state.turn += 1
    choice = next(c for c in node.choices if c.key == key)
    state.emit(type="choice", node=node.id, label=choice.label)
    if choice.check:
        ok = _resolve_check(state, choice.check)
        dest = choice.on_success if ok else choice.on_failure
    else:
        dest = choice.next
    _goto(state, dest)
    return None


def _handle_combat(state: GameState, controller, node) -> str | None:
    """戦闘ノードを解決する。終局なら "clear"/"defeat" を、継続なら None を返す。"""
    sc = state.scenario
    first_free = node.recon_free_first and has_recon(state)
    res = run_combat(state, node.id, controller, first_free_hit=first_free)
    if res == "win":
        _goto(state, node.on_win)
        dest = sc.node(node.on_win)
        if dest.kind == "ending" and dest.ending:
            state.emit(type="ending", result=dest.ending)
            return dest.ending
        return None
    if res == "fled":
        _goto(state, sc.start_node)
        return None
    # defeat
    if state.respawn_on_defeat:
        # 崩れ落ちる描写は combat の defeat イベントで presenter が出す。
        # HP 半分では詰みうるので全快とし、村の探索フェーズからやり直す（死なない設計）。
        state.clear_focused_object()
        state.reset_for_village()
        state.emit(type="respawn", hp=state.hp, mp=state.mp)
        _run_village(state, controller)      # 探索を選び直す（on_defeat_return: village）
        state.clear_focused_object()          # village から本編へ移る境界
        state.turn += 1
        _goto(state, sc.start_node)
        return None
    state.emit(type="ending", result="defeat")
    return "defeat"


def run_session(state: GameState, controller) -> str:
    """シナリオのノードグラフを歩く。戻り値: "clear" / "defeat"。

    ノード種別（decision / combat / ending）で分岐するだけの汎用ループ。
    ノードの中身・遷移・敵・判定目標はすべてシナリオ(state.scenario)から来る。"""
    sc = state.scenario
    if not state.started:
        state.started = True
        state.emit(type="session_start", seed=state.seed)
        _run_village(state, controller)
        state.clear_focused_object()          # village から本編へ移る境界
        state.turn += 1
        _goto(state, sc.start_node)

    while True:
        node = sc.node(state.node)
        if node.kind == "decision":
            if _handle_decision(state, controller, node) == RELOAD:
                continue
        elif node.kind == "combat":
            res = _handle_combat(state, controller, node)
            if res:
                return res
        elif node.kind == "ending":
            # 決定ノードから直接エンディングへ来た場合（combat 経由は上で return 済み）。
            result = node.ending or "clear"
            state.emit(type="ending", result=result)
            return result
        else:
            raise RuntimeError(f"未知のノード種別: {node.kind}（{node.id}）")


# ---------------------------------------------------------------------------
# ヘッドレス実行のヘルパ
# ---------------------------------------------------------------------------

def run_scripted(seed, explores, node_choices, combat_cmds, respawn=False,
                 scenario_id=DEFAULT_SCENARIO) -> GameState:
    """入力列を再生してログを生成する（回帰・検証用）。"""
    state = GameState(seed, scenario=load_scenario(scenario_id))
    state.respawn_on_defeat = respawn
    controller = ScriptedController(explores, node_choices, combat_cmds)
    run_session(state, controller)
    return state


def run_policy(seed, build, scenario_id=DEFAULT_SCENARIO) -> tuple[str, GameState]:
    """方針でヘッドレス自動プレイ（simulate 用）。"""
    state = GameState(seed, scenario=load_scenario(scenario_id))
    state.respawn_on_defeat = False
    controller = PolicyController(build)
    result = run_session(state, controller)
    return result, state


def write_log(state: GameState, path: str | None = None) -> str:
    os.makedirs(LOG_DIR, exist_ok=True)
    if path is None:
        path = os.path.join(LOG_DIR, f"session_{state.seed}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state.log, f, ensure_ascii=False, indent=1)
    return path


# ---------------------------------------------------------------------------
# 対話コントローラ（コンソール）
# ---------------------------------------------------------------------------

class ConsoleController:
    """人間がキーボードで選ぶ。状態への参照を持ち、status/save/load/quit を捌く。"""

    def __init__(self, state: GameState, save_dir: str, ui_mode: str = "menu"):
        self.state = state
        self.save_dir = save_dir
        self.ui_mode = ui_mode
        self.tui = None
        if ui_mode == "tui":
            from .tui import TerminalUI
            self.tui = TerminalUI()
        # 判定結果・敵ターン・敗北描写を「起きた順」に画面へ出す（表示専用フック）。
        state.presenter = self.present_event

    def _tui_active(self):
        return self.tui is not None and self.tui.can_render()

    def _message(self, text):
        """対話表示だけを出力する。ゲーム状態・ログには書かない。"""
        if self._tui_active():
            self.tui.messages.add(text)
        else:
            print(text)

    def announce(self, text):
        self._message(text)

    def _recovery_item_name(self):
        for key in self.state.scenario.village_order:
            opt = self.state.scenario.village_option(key)
            eff = opt.get("effect") or {}
            if eff.get("type") == "item" and eff.get("item") == "herb":
                gain = opt.get("gain", "")
                if "薬草" in gain:
                    return "薬草"
                if "傷薬" in gain:
                    return "傷薬"
        return "回復薬"

    def _pending_recovery(self, picked):
        count = 0
        for key in picked:
            eff = (self.state.scenario.village_option(key).get("effect") or {})
            if eff.get("type") == "item" and eff.get("item") == "herb":
                count += int(eff.get("count", 0))
        return count

    def _status_line(self, pending_recovery=0):
        s = self.state
        item = self._recovery_item_name()
        pending = f"（持込予定 {pending_recovery}）" if pending_recovery else ""
        return f"HP {s.hp}/{s.hp_max}  MP {s.mp}/{s.mp_max}  {item} {s.herbs}{pending}"

    def _draw_tui(self, place, situation, objective, menu, scene="", pending_recovery=0,
                  *, scene_kind="", scene_id=None, enemies=(), preparation=None,
                  game_map=None, ending=None):
        if self.tui is None:
            return False
        from .presentation import (
            ActionView, PresentationContext, build_enemy_views, build_map_view,
            build_render_snapshot,
        )
        from .tui import screen_model_from_snapshot
        actions = tuple(
            ActionView(canonical_command=command, kind=scene_kind or "action",
                       label=label, detail=detail)
            for label, command, detail in menu
        )
        context = PresentationContext(
            scene_kind=scene_kind,
            scene_id=scene_id,
            scene_title=place,
            scene_text=scene,
            objective=objective,
            recovery_item_name=self._recovery_item_name(),
            pending_recovery_count=pending_recovery,
            actions=actions,
            enemies=build_enemy_views(enemies),
            preparation=preparation,
            map=build_map_view(game_map) if game_map is not None else None,
            recent_messages=self.tui.messages.messages(),
            ending=ending,
        )
        model = screen_model_from_snapshot(build_render_snapshot(self.state, context))
        return self.tui.draw(model)

    # --- 入力案内（表示専用。状態・ログ・乱数には触れない） ---
    @staticmethod
    def _show_compact_menu(place, situation, objective, menu):
        print()
        print("─" * 40)
        print(f"{place}　{situation}")
        print(f"目的: {objective}")
        print()
        for i, (label, _command, _detail) in enumerate(menu, 1):
            print(f"{i}) {label}")
        print()
        print("[S] 状態  [H] ヘルプ  [Q] 終了")

    def _help_lines(self, menu, include_load=True):
        lines = ["数字または [コマンド] を直接入力できる。"]
        for i, (label, command, detail) in enumerate(menu, 1):
            lines.append(f"{i}) {label} — {detail} [{command}]")
        lines.extend([
            "S / status — H の状態を表示",
            "H / help — このヘルプを表示",
            "Q / quit — ゲームを中断",
            "save <名前> — 現在の状態を保存（例: save camp）",
        ])
        if include_load:
            lines.append("load <名前> — 保存した状態を読込（例: load camp）")
        else:
            lines.append("load は戦闘外で使用する。")
        lines.append("地図では go <方角> または方角単独も使用できる。")
        return lines

    def _show_help(self, menu, include_load=True):
        lines = self._help_lines(menu, include_load)
        if self.tui is not None and self.tui.draw_help(lines):
            input("Enterで戻る > ")  # UI専用。RecordingControllerへは渡らない。
            return
        print()
        print("── ヘルプ ──")
        for line in lines:
            print(f"  {line}")

    @staticmethod
    def _menu_command(raw, menu):
        token = parse_raw_input(raw)
        return ConsoleController._command_from_token(token, menu, raw=raw)

    @staticmethod
    def _meta_shortcut(raw):
        # 小文字 s は既存の south。メタ短縮は大文字だけを扱う。
        token = parse_raw_input(raw)
        if raw in ("S", "H", "Q") and isinstance(token, MetaRequest):
            return token.command
        return raw

    @staticmethod
    def _read_input_token(prompt="選択 > "):
        raw = input(prompt).strip()
        return raw, parse_raw_input(raw)

    @staticmethod
    def _command_from_token(token, menu=(), *, raw=None, normalize_direct=True):
        if token is None:
            return raw if raw is not None else ""
        if isinstance(token, SelectMenuIndex):
            command = resolve_menu_index(token, tuple(item[1] for item in menu))
            return command if command is not None else (raw if raw is not None else "")
        if isinstance(token, DirectCommand):
            return token.text if normalize_direct else (raw if raw is not None else token.text)
        if isinstance(token, MetaRequest):
            return (f"{token.command} {token.argument}"
                    if token.argument is not None else token.command)
        return ""

    @staticmethod
    def _legacy_meta_command(raw, token, *, casefold):
        """MetaRequestを場面ごとの従来case規則で既存_meta()入力へ戻す。"""
        if not isinstance(token, MetaRequest):
            return None
        if raw in ("S", "H", "Q"):
            return token.command
        head = raw.split(maxsplit=1)[0] if raw else ""
        if token.command == "help" and head.lower() == "help":
            pass
        elif not casefold and head != token.command:
            return None
        command = (f"{token.command} {token.argument}"
                   if token.argument is not None else token.command)
        return command.lower() if casefold else command

    def _village_menu(self, gm, sc, picked):
        loc = gm.here()
        menu = []
        if (loc.action and loc.action not in picked
                and len(picked) < sc.village_pick_count):
            opt = sc.village_option(loc.action)
            menu.append((opt["name"], "do", "この場所で支度を行う"))
        if loc.leads_to_adventure and len(picked) >= sc.village_pick_count:
            destination = self._departure_destination(sc)
            menu.append((f"{destination}へ向かう", "depart", "拠点から冒険へ出立する"))
        exits = gm.exits()
        for direction in _DIR_ORDER:
            if direction in exits:
                dest = gm.dest_name(direction)
                menu.append((f"{_DIR_LABEL[direction]}へ → {dest}", f"go {direction}",
                             f"{dest}へ移動する"))
        menu.append(("周囲を見る", "look", "現在地と周囲の地図を表示する"))
        return menu

    def _show_village_menu(self, gm, sc, picked, menu):
        from .presentation import PreparationView
        remaining = sc.village_pick_count - len(picked)
        objective = (f"支度をあと {remaining} つ整える" if remaining > 0
                     else f"{self._departure_destination(sc)}へ向かう")
        if self._draw_tui(
                gm.here().name, f"支度 {len(picked)}/{sc.village_pick_count}",
                objective, menu, scene=self._map_text(gm),
                pending_recovery=self._pending_recovery(picked), scene_kind="village",
                game_map=gm,
                preparation=PreparationView(
                    selected_keys=tuple(picked), selected_count=len(picked),
                    required_count=sc.village_pick_count,
                    pending_recovery_count=self._pending_recovery(picked),
                    ready_to_depart=len(picked) >= sc.village_pick_count,
                )):
            return
        self._show_compact_menu(
            gm.here().name, f"支度 {len(picked)}/{sc.village_pick_count}", objective, menu,
        )

    @staticmethod
    def _departure_destination(sc):
        node = sc.node(sc.start_node)
        return node.title or "冒険"

    @staticmethod
    def _choice_menu(node):
        return [(c.label, str(i), "この行動を選ぶ")
                for i, c in enumerate(node.choices, 1)]

    def _list_village_menu(self, sc, picked):
        return [
            (sc.village_option(key)["name"], str(i), "出立前の支度として選ぶ")
            for i, key in enumerate(sc.village_order, 1) if key not in picked
        ]

    def _show_list_village_menu(self, sc, picked, menu):
        from .presentation import PreparationView
        remaining = sc.village_pick_count - len(picked)
        if self._draw_tui(
                "出立前の拠点", f"支度 {len(picked)}/{sc.village_pick_count}",
                f"支度をあと {remaining} つ選ぶ", menu,
                scene="未選択の支度を番号で選ぶ", scene_kind="village",
                preparation=PreparationView(
                    selected_keys=tuple(picked), selected_count=len(picked),
                    required_count=sc.village_pick_count,
                    pending_recovery_count=self._pending_recovery(picked),
                    ready_to_depart=len(picked) >= sc.village_pick_count,
                )):
            return
        self._show_compact_menu(
            "出立前の拠点", f"支度 {len(picked)}/{sc.village_pick_count}",
            f"支度をあと {remaining} つ選ぶ", menu,
        )

    def _combat_options(self, state):
        opts = ["attack"]
        if state.mp >= MP_COST:
            opts.append("magic")
        if state.herbs > 0:
            opts.append("herb")
        opts.append("flee")
        return opts

    def _combat_menu(self, state, enemies):
        alive = [e for e in enemies if e.alive]
        target = alive[0] if alive else None
        target_name = target.name_ja if target else "敵"
        menu = [
            (f"攻撃 → {target_name}（自動）", "attack", "先頭の生存敵を武器で攻撃する"),
        ]
        if state.mp >= MP_COST:
            menu.append((f"魔法 → {target_name}（自動）", "magic",
                         f"MPを {MP_COST} 消費して先頭の生存敵を攻撃する"))
        if state.herbs > 0:
            item = self._recovery_item_name()
            menu.append((f"{item}を使う", "herb", f"{item}を使ってHPを回復する"))
        menu.append(("逃げる", "flee", "戦闘からの離脱を試みる"))
        return menu

    def _show_combat_menu(self, state, enemies, menu):
        alive = [e for e in enemies if e.alive]
        situation = " / ".join(f"{e.name_ja} HP{max(0, e.hp)}" for e in alive)
        if self._draw_tui(
                self.state.scenario.node(self.state.node).title or "戦闘",
                situation or "敵なし", "敵を退けるか離脱する", menu,
                scene=f"自動対象: {alive[0].name_ja}" if alive else "敵なし",
                scene_kind="combat", scene_id=self.state.node, enemies=enemies):
            return
        self._show_compact_menu(
            self.state.scenario.node(self.state.node).title or "戦闘",
            situation or "敵なし", "敵を退けるか離脱する", menu,
        )

    # --- 探索フェーズ（対話・敗北後もここに戻る＝Fix3） ---
    #     地図がある場合は「歩いて回る」UI。無ければ従来のリスト選択にフォールバック。
    #     ★どちらでも返り値は「選んだ探索 key の列」。run_session が village.explore で
    #       適用する（d6 消費順＝この列の順）。地図は探索を選ぶ UI の変更にすぎない。
    def explores(self):
        sc = self.state.scenario
        if not getattr(sc, "has_map", False):
            self._message(
                f"支度 — 出立の前に、{len(sc.village_order)} つから "
                f"{sc.village_pick_count} つ選ぶ"
            )
            return list_explore_and_pick(self)
        return self._walk_village(sc)

    def _walk_village(self, sc):
        from .map import build_map
        if not self.state.location:
            self.state.transition_location(sc.map_start)
        gm = build_map(sc, self.state.location)
        picked: list[str] = []
        pick_count = sc.village_pick_count
        self._message(f"拠点で支度する（{pick_count} つ整えて、出口から出立）")
        self._show_here(gm, sc, picked)
        while len(picked) <= pick_count:
            self.state.transition_location(gm.current)  # 保存点で現在地を最新化
            menu = self._village_menu(gm, sc, picked)
            self._show_village_menu(gm, sc, picked, menu)
            original, token = self._read_input_token()
            raw = self._command_from_token(token, menu, raw=original)
            low = raw.lower() if raw is not None else ""
            if low == "help":
                self._show_help(menu)
                continue
            meta = self._meta(low)
            if meta == RELOAD:
                gm.current = self.state.location       # ロードで現在地を復元
                self._show_here(gm, sc, picked)
                continue
            if meta == "quit":
                self._message("中断する。"); sys.exit(0)
            if meta == "handled":
                continue
            parts = low.split()
            cmd = parts[0] if parts else ""
            direction = (resolve_direction(low)
                         if len(parts) == 1 or cmd in ("go", "move", "g", "walk")
                         else None)
            if cmd in ("look", "map", "m", "l"):
                self._show_here(gm, sc, picked)
            elif direction is not None:
                self._try_move(gm, sc, picked, direction)
            elif cmd in ("do", "explore", "search", "action", "x", "調べる", "聞く"):
                self._do_action(gm, sc, picked, pick_count)
            elif cmd in ("depart", "leave", "forest", "森", "発つ"):
                if self._try_depart(gm, sc, picked, pick_count):
                    return picked
            else:
                self._message("その選択は使用できません。")
        return picked

    def _try_move(self, gm, sc, picked, direction):
        if gm.move(direction):
            self.state.transition_location(gm.current)
            self._message(f"{gm.here().name}へ移動した。")
            self._show_here(gm, sc, picked)
        else:
            self._message("そちらへは道がない。")

    def _do_action(self, gm, sc, picked, pick_count):
        key = gm.here().action
        if not key:
            self._message("ここで特にできることはない。歩いて回ろう。")
            return
        if key in picked:
            self._message("それはもう済ませた。")
            return
        if len(picked) >= pick_count:
            self._message(f"支度はもう {pick_count} つ整えた。出口から出立しよう。")
            return
        opt = sc.village_option(key)
        picked.append(key)
        self._message(opt.get("text", ""))
        self._message(f"{opt['name']}：{opt.get('gain', '')}／支度 {len(picked)}/{pick_count}")

    def _try_depart(self, gm, sc, picked, pick_count):
        if not gm.here().leads_to_adventure:
            self._message("ここからは出立できない。出口まで移動しよう。")
            return False
        if len(picked) < pick_count:
            self._message(f"まだ支度が {pick_count - len(picked)} つ残っている。")
            return False
        self._message(f"{self._departure_destination(sc)}へ向けて出立した。")
        return True

    @staticmethod
    def _map_text(gm):
        from .map_view import render_map
        return render_map(gm)

    def _show_here(self, gm, sc, picked):
        if self._tui_active():
            return
        print()
        print(self._map_text(gm))
        loc = gm.here()
        if loc.action:
            opt = sc.village_option(loc.action)
            mark = "済" if loc.action in picked else "未"
            print(f"  ここで: {opt['name']}（{opt.get('gain', '')}）[{mark}] —— 'do' で行う")
        if loc.leads_to_adventure:
            print(f"  ここから 'depart' で{self._departure_destination(sc)}へ向かえる。")
        print(f"  支度 {len(picked)}/{sc.village_pick_count}")

    # --- 判定・戦闘の結果表示（Fix1）／敗北描写（Fix2） ---
    #     ここは state.log から読む「表示層」。ログ・乱数・判定には一切触れない。
    def present_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "encounter":
            self._show_encounter(ev)
        elif t == "check":
            self._show_check(ev)
        elif t == "mp_cost":
            self._message(f"魔力を {ev['cost']} 消費（残 MP {ev['mp']}）")
        elif t == "player_attack":
            self._show_player_attack(ev)
        elif t == "enemy_attack":
            self._show_enemy_attack(ev)
        elif t == "herb":
            item = self._recovery_item_name()
            self._message(f"{item}を使う — HP+{ev['heal']}（HP {ev['hp']}／残 {item} {ev['herbs']}）")
        elif t == "combat_win":
            self._message("敵を退けた。")
        elif t == "defeat":
            if not self.state.respawn_on_defeat:
                self._message("H は膝から崩れ落ちた。意識が遠のく——")
        elif t == "respawn":
            text = self.state.scenario.ending_text("defeat")
            self._message(text or "気がつくと拠点へ戻されていた。支度を整え直そう。")

    def _show_encounter(self, ev):
        sc = self.state.scenario
        txt = sc.node_text(ev["node"])
        if txt:
            self._message(txt)
        names = "／".join(sc.enemy_name(k) for k in ev["enemies"])
        self._message(f"戦闘 — {names}")

    def _show_check(self, ev):
        tag = ev.get("tag")
        label = {
            "sneak": "藪を抜ける〔vit〕",
            "vit_check": "松明を消して忍ぶ〔vit〕",
            "flee": "離脱をはかる〔vit〕",
            "free_hit": "偵察の一手",
            "attack_attack": "H の斬撃〔str〕",
            "magic_attack": "H の呪〔mag〕",
        }.get(tag) or self._scenario_check_label(tag)
        # 成否の語を判定種別に合わせる
        if tag in ("attack_attack", "magic_attack", "free_hit"):
            ok, ng = "命中", "外れ"
        elif tag == "flee":
            ok, ng = "振り切った", "逃げ損ねた"
        else:
            ok, ng = "成功", "失敗"
        if ev.get("auto"):
            self._message(f"{label} — {ok}（自動）")
            return
        dice = ev["dice"]
        mod = ev["modifier"]
        sign = f"+{mod}" if mod >= 0 else str(mod)
        if ev.get("crit"):
            result = "会心（6ゾロ・自動成功）"
        elif ev.get("fumble"):
            result = "大失敗（1ゾロ・自動失敗）"
        else:
            result = ok if ev["success"] else ng
        self._message(f"{label}: 2D6[{dice[0]},{dice[1]}]={ev['sum']} {sign} "
                      f"→ {ev['total']} vs 目標{ev['target']} → {result}")

    def _show_player_attack(self, ev):
        if ev.get("damage", 0) > 0:
            crit = "（会心！）" if ev.get("crit") else ""
            self._message(f"{self.state.scenario.enemy_name(ev['target'])} に "
                          f"{ev['damage']} ダメージ{crit}（残 HP {ev['enemy_hp']}）")
        # 外れは check 行が「外れ」と出しているので、ここでは重ねない。

    def _show_enemy_attack(self, ev):
        d = ev["dice"]
        name = self.state.scenario.enemy_name(ev["enemy"])
        if ev["hit"]:
            self._message(f"{name} の攻撃 [{d[0]},{d[1]}]={ev['total']} "
                          f"→ {ev['damage']} ダメージを受けた（HP {ev['player_hp']}）")
        else:
            self._message(f"{name} の攻撃 [{d[0]},{d[1]}]={ev['total']} → かわした")

    # --- 内心表示（I-4: H にだけ見えているもの） ---
    def _show_status(self):
        s = self.state
        self._message("H の内心（転生者にだけ見える数値・I-4）")
        self._message(f"HP {s.hp}/{s.hp_max}  MP {s.mp}/{s.mp_max}  "
                      f"{self._recovery_item_name()} {s.herbs}")
        self._message(f"str {s.str}(+{modifier(s.str)})  mag {s.mag}(+{modifier(s.mag)})  "
                      f"vit {s.vit}(+{modifier(s.vit)})")
        self._message(f"授かり: {', '.join(s.buff_labels) if s.buff_labels else 'なし'}")

    def _scenario_check_label(self, tag):
        matches = []
        for node in self.state.scenario.nodes.values():
            for choice in node.choices:
                check = choice.check or {}
                if check.get("tag") == tag:
                    matches.append((choice.label, check.get("stat")))
        if len(matches) != 1:
            return "判定"
        label, stat = matches[0]
        label = label.split("【", 1)[0].strip()
        return f"{label}〔{stat}〕" if stat else label

    def _save(self, name):
        os.makedirs(self.save_dir, exist_ok=True)
        path = os.path.join(self.save_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.state.snapshot(), f, ensure_ascii=False, indent=1)
        self._message(f"[セーブ] {path}")

    def _load(self, name) -> bool:
        path = os.path.join(self.save_dir, f"{name}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                snap = json.load(f)
        except OSError:
            self._message(f"[ロード失敗] {path} が見つからない")
            return False
        self.state.restore(snap)
        self._message(f"[ロード] {path}（rng 状態も復元）")
        return True

    def _meta(self, cmd) -> str | None:
        """メタコマンドを処理。処理したら 'handled'、load 成功なら RELOAD、quit なら 'quit'。"""
        parts = cmd.split()
        if not parts:
            return "handled"
        head = parts[0]
        if head == "status":
            self._show_status(); return "handled"
        if head == "save" and len(parts) >= 2:
            self._save(parts[1]); return "handled"
        if head == "load" and len(parts) >= 2:
            return RELOAD if self._load(parts[1]) else "handled"
        if head == "quit":
            return "quit"
        return None

    def choice(self, node, options):
        sc = self.state.scenario
        n = sc.node(node)
        txt = sc.node_text(node)
        if txt and not self._tui_active():
            print()
            print(txt)
        labels = [(c.key, c.label) for c in n.choices]
        menu = self._choice_menu(n)
        while True:
            if not self._draw_tui(
                    n.title or n.id, "行動を選択", "次に取る行動を一つ選ぶ",
                    menu, scene=txt, scene_kind="decision", scene_id=n.id):
                self._show_compact_menu(
                    n.title or n.id, "行動を選択", "次に取る行動を一つ選ぶ", menu,
                )
            original, token = self._read_input_token()
            raw = self._command_from_token(
                token, menu, raw=original, normalize_direct=False,
            )
            meta_command = self._legacy_meta_command(original, token, casefold=False)
            if meta_command is not None:
                raw = meta_command
            elif isinstance(token, MetaRequest):
                raw = original
            if raw.lower() == "help":
                self._show_help(menu)
                continue
            meta = self._meta(raw)
            if meta == RELOAD:
                return RELOAD
            if meta == "quit":
                self._message("中断する。"); sys.exit(0)
            if meta == "handled":
                continue
            if raw.isdigit() and 1 <= int(raw) <= len(labels):
                return labels[int(raw) - 1][0]
            self._message("その選択は使用できません。")

    def combat_command(self, state, enemies):
        alive = [e for e in enemies if e.alive]
        if not self._tui_active():
            print()
            print("  ▼ 戦闘 —— " + " / ".join(f"{e.name_ja}(HP{max(0, e.hp)})" for e in alive))
            print(f"     H: HP {state.hp}/{state.hp_max}  MP {state.mp}/{state.mp_max}  "
                  f"{self._recovery_item_name()} {state.herbs}")
        while True:
            opts = self._combat_options(state)
            menu = self._combat_menu(state, enemies)
            self._show_combat_menu(state, enemies, menu)
            original, token = self._read_input_token()
            if (isinstance(token, MetaRequest)
                    and token.command == "load" and token.argument):
                self._message("戦闘中のロードは非対応。安全な選択肢で load を。")
                continue
            raw = self._command_from_token(token, menu, raw=original)
            raw = raw.lower() if raw is not None else ""
            if raw == "help":
                self._show_help(menu, include_load=False)
                continue
            meta = self._meta(raw)
            if meta == RELOAD:
                self._message("戦闘中のロードは非対応。安全な選択肢で load を。")
                continue
            if meta == "quit":
                self._message("中断する。"); sys.exit(0)
            if meta == "handled":
                continue
            combat_command = resolve_combat_command(raw, allowed=opts)
            if combat_command is not None:
                return combat_command
            if raw == "magic" and state.mp < MP_COST:
                self._message(f"MP が足りない（{MP_COST} 必要・I-2）。魔法は選べない。")
                continue
            self._message("その選択は使用できません。")


def play_interactive(seed: int, scenario_id: str = DEFAULT_SCENARIO, ui_mode: str = "menu"):
    scenario = load_scenario(scenario_id)
    state = GameState(seed, scenario=scenario)
    state.respawn_on_defeat = True
    save_dir = os.path.join(LOG_DIR, "saves")
    controller = ConsoleController(state, save_dir, ui_mode=ui_mode)
    if controller._tui_active():
        controller.announce(f"Ordia — {scenario.title}（seed={seed}・LLM 不使用）")
        if scenario.intro:
            controller.announce(scenario.intro)
    else:
        print("=" * 60)
        print(f"  Ordia — {scenario.title}（seed={seed}・LLM 不使用）")
        print("=" * 60)
        if scenario.intro:
            print(scenario.intro)
    # 探索フェーズは run_session が controller.explores() を呼んで進める
    # （敗北後もそこへ戻る＝Fix3）。番号で選ぶ。
    result = run_session(state, controller)
    print()
    print(scenario.ending_text(result))
    print(f"\n>>> 結果: {result}")
    path = write_log(state)
    print(f">>> ログ: {path}")


def list_explore_and_pick(controller: ConsoleController):
    sc = controller.state.scenario
    order = sc.village_order
    pick_count = sc.village_pick_count
    picked = []
    while len(picked) < pick_count:
        menu = controller._list_village_menu(sc, picked)
        controller._show_list_village_menu(sc, picked, menu)
        original, token = controller._read_input_token()
        raw = controller._command_from_token(
            token, menu, raw=original, normalize_direct=False,
        )
        meta_command = controller._legacy_meta_command(original, token, casefold=False)
        if meta_command is not None:
            raw = meta_command
        elif isinstance(token, MetaRequest):
            raw = original
        if raw.lower() == "help":
            controller._show_help(menu)
            continue
        meta = controller._meta(raw)
        if meta == "quit":
            sys.exit(0)
        if meta == "handled":
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(order):
            key = order[int(raw) - 1]
            if key in picked:
                controller._message("それは選択済み。")
                continue
            picked.append(key)
            controller._message(sc.village_option(key).get("text", ""))
        else:
            controller._message("その選択は使用できません。")
    return picked


# ---------------------------------------------------------------------------
# 参照入力列（seed=7 / クリア）
# ---------------------------------------------------------------------------

REFERENCE_SEED7 = {
    "seed": 7,
    "explores": ["elder", "herbs", "scout"],
    "node_choices": ["bush", "cave", "sneak"],
    "combat_cmds": ["attack", "attack", "attack", "attack",
                    "magic", "magic", "magic", "magic", "magic"],
}


def main(argv):
    ap = argparse.ArgumentParser(description="決定論 TRPG セッション（LLM 不使用）。")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--scenario", default=DEFAULT_SCENARIO,
                    help="scenarios/<id>.yaml を選ぶ（既定: goblin）")
    ap.add_argument("--ui", choices=("menu", "tui"), default="menu",
                    help="対話UI（既定: menu）")
    ap.add_argument("--replay", action="store_true", help="seed=7 の参照入力列を自動再生してログ出力")
    args = ap.parse_args(argv)

    if args.replay:
        ref = REFERENCE_SEED7
        state = run_scripted(ref["seed"], ref["explores"], ref["node_choices"],
                             ref["combat_cmds"], scenario_id=args.scenario)
        path = write_log(state)
        print(f"replay seed={ref['seed']} scenario={args.scenario} → {path}"
              f"（{len(state.log)} events, ending={state.log[-1].get('result')}）")
        return 0

    play_interactive(args.seed, scenario_id=args.scenario, ui_mode=args.ui)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
