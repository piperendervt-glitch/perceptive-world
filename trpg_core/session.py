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

from .combat import run_combat
from .rng import Rng
from .rules import DEFAULT_CHAR, MP_COST, modifier, roll
from .scenario import (
    CAVE_HALL_CHOICES,
    COMBAT_ENEMIES,
    COMBAT_NEXT,
    FOREST_CHOICES,
    SNEAK_CONTINUE,
    SNEAK_TARGET,
    node_text,
)

# Windows console default cp932 chokes on CJK output; force UTF-8（resolve.py と同流儀）。
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
RELOAD = "__reload__"


# ---------------------------------------------------------------------------
# キャラクター読み込み（canon/status.yaml は読むだけ。書き戻さない）
# ---------------------------------------------------------------------------

def load_character() -> dict:
    """canon/status.yaml から H を読む（max を全快の初期値とする）。読めなければ DEFAULT_CHAR。"""
    path = os.path.join(os.path.dirname(__file__), os.pardir, "canon", "status.yaml")
    try:
        import yaml  # 任意依存。無ければフォールバック。
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        h = data["characters"]["H"]
        attrs = h["attributes"]
        return {
            "hp_max": int(h["hp"]["max"]),
            "mp_max": int(h["mp"]["max"]),
            "str": int(attrs["str"]),
            "mag": int(attrs["mag"]),
            "vit": int(attrs["vit"]),
        }
    except Exception:
        return dict(DEFAULT_CHAR)


# ---------------------------------------------------------------------------
# ゲーム状態
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self, seed: int, char: dict | None = None):
        char = char or load_character()
        self.seed = seed
        self.rng = Rng(seed)
        self.hp_max = char["hp_max"]
        self.mp_max = char["mp_max"]
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.str = char["str"]
        self.mag = char["mag"]
        self.vit = char["vit"]
        # 探索で得るボーナス（I-4: H の内心にだけ映る）
        self.elder = False       # 頭目への命中 +2
        self.blessing = False    # 全命中 +1
        self.dagger = False      # 物理ダメージ +2
        self.scout = False       # 藪自動成功 / 見張り初撃必中
        self.herbs = 0           # 薬草の数
        # 進行
        self.turn = 0
        self.node = "forest"
        self.started = False
        self.respawn_on_defeat = False
        self.log: list[dict] = []

    def emit(self, **fields) -> dict:
        entry = {"t": self.turn}
        entry.update(fields)
        self.log.append(entry)
        return entry

    # --- save/load（★rng の内部状態 a を含む＝ロード後の乱数列が一致する） ---
    _SNAP_FIELDS = (
        "seed", "hp_max", "mp_max", "hp", "mp", "str", "mag", "vit",
        "elder", "blessing", "dagger", "scout", "herbs",
        "turn", "node", "started", "respawn_on_defeat",
    )

    def snapshot(self) -> dict:
        snap = {k: getattr(self, k) for k in self._SNAP_FIELDS}
        snap["rng_a"] = self.rng.state()
        return snap

    def restore(self, snap: dict) -> None:
        for k in self._SNAP_FIELDS:
            if k in snap:
                setattr(self, k, snap[k])
        self.rng.set_state(snap["rng_a"])


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

def run_session(state: GameState, controller) -> str:
    """フローを最後まで回す。戻り値: "clear" / "defeat"（respawn 時は defeat を返さず継続）。"""
    if not state.started:
        state.started = True
        state.emit(type="session_start", seed=state.seed)
        from . import village
        for k in controller.explores():
            village.explore(state, k)
        state.turn += 1
        state.emit(type="enter_node", node="forest")
        state.node = "forest"

    while True:
        node = state.node

        if node == "forest":
            key = controller.choice("forest", [c[0] for c in FOREST_CHOICES])
            if key == RELOAD:
                continue
            state.turn += 1
            state.emit(type="choice", node="forest", label=dict(FOREST_CHOICES)[key])
            if key == "bush":
                if state.scout:
                    state.emit(type="check", tag="sneak", auto=True, success=True)
                    state.node = "sneak_ok"
                else:
                    rr = roll(state.rng, modifier(state.vit), SNEAK_TARGET)
                    state.emit(type="check", tag="sneak", **rr)
                    state.node = "sneak_ok" if rr["success"] else "sneak_fail"
                state.emit(type="enter_node", node=state.node)
            else:  # road
                state.emit(type="enter_node", node="cave_entrance")
                state.node = "cave_entrance"

        elif node in ("sneak_ok", "sneak_fail"):
            key = controller.choice(node, ["cave"])
            if key == RELOAD:
                continue
            state.turn += 1
            state.emit(type="choice", node=node, label=SNEAK_CONTINUE[0][1])
            state.emit(type="enter_node", node="cave_entrance")
            state.node = "cave_entrance"

        elif node == "cave_hall":
            key = controller.choice("cave_hall", [c[0] for c in CAVE_HALL_CHOICES])
            if key == RELOAD:
                continue
            state.turn += 1
            state.emit(type="choice", node="cave_hall", label=dict(CAVE_HALL_CHOICES)[key])
            if key == "sneak":
                mod = modifier(state.vit) + (2 if state.scout else 0)
                rr = roll(state.rng, mod, SNEAK_TARGET)
                state.emit(type="check", tag="vit_check", **rr)
                state.node = "hall1" if rr["success"] else "hall2"
            else:  # front
                state.node = "hall2"
            state.emit(type="enter_node", node=state.node)

        elif node in COMBAT_ENEMIES:  # cave_entrance / hall1 / hall2 / depths
            first_free = state.scout and node == "cave_entrance"
            res = run_combat(state, node, controller, first_free_hit=first_free)
            if res == "win":
                nxt = COMBAT_NEXT[node]
                if nxt == "win":
                    state.emit(type="enter_node", node="win")
                    state.emit(type="ending", result="clear")
                    return "clear"
                state.emit(type="enter_node", node=nxt)
                state.node = nxt
            elif res == "fled":
                state.emit(type="enter_node", node="forest")
                state.node = "forest"
            else:  # defeat
                if state.respawn_on_defeat:
                    state.hp = max(1, state.hp_max // 2)
                    state.mp = state.mp_max
                    state.emit(type="enter_node", node="defeat")
                    state.emit(type="respawn", hp=state.hp, mp=state.mp)
                    state.emit(type="enter_node", node="forest")
                    state.node = "forest"
                else:
                    state.emit(type="ending", result="defeat")
                    return "defeat"
        else:
            raise RuntimeError(f"未知のノード: {node}")


# ---------------------------------------------------------------------------
# ヘッドレス実行のヘルパ
# ---------------------------------------------------------------------------

def run_scripted(seed, explores, node_choices, combat_cmds, respawn=False) -> GameState:
    """入力列を再生してログを生成する（回帰・検証用）。"""
    state = GameState(seed)
    state.respawn_on_defeat = respawn
    controller = ScriptedController(explores, node_choices, combat_cmds)
    run_session(state, controller)
    return state


def run_policy(seed, build) -> tuple[str, GameState]:
    """方針でヘッドレス自動プレイ（simulate 用）。"""
    state = GameState(seed)
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

    def __init__(self, state: GameState, save_dir: str):
        self.state = state
        self.save_dir = save_dir

    # --- 内心表示（I-4: H にだけ見えているもの） ---
    def _show_status(self):
        s = self.state
        print("  ── H の内心（転生者にだけ見える数値・I-4）──")
        print(f"     HP {s.hp}/{s.hp_max}   MP {s.mp}/{s.mp_max}   薬草 {s.herbs}")
        print(f"     str {s.str}(+{modifier(s.str)})  mag {s.mag}(+{modifier(s.mag)})  vit {s.vit}(+{modifier(s.vit)})")
        buffs = []
        if s.elder: buffs.append("村長の助言(頭目命中+2)")
        if s.blessing: buffs.append("祝福(命中+1)")
        if s.dagger: buffs.append("錆びた短剣(物理+2)")
        if s.scout: buffs.append("偵察(藪自動/初撃必中)")
        print(f"     授かり: {', '.join(buffs) if buffs else 'なし'}")

    def _save(self, name):
        os.makedirs(self.save_dir, exist_ok=True)
        path = os.path.join(self.save_dir, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.state.snapshot(), f, ensure_ascii=False, indent=1)
        print(f"  [セーブ] {path}")

    def _load(self, name) -> bool:
        path = os.path.join(self.save_dir, f"{name}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                snap = json.load(f)
        except OSError:
            print(f"  [ロード失敗] {path} が見つからない")
            return False
        self.state.restore(snap)
        print(f"  [ロード] {path}（rng 状態も復元）")
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
        print()
        print(node_text(node))
        labels = self._labels(node, options)
        while True:
            for i, (_k, lbl) in enumerate(labels, 1):
                print(f"  {i}) {lbl}")
            raw = input("> ").strip()
            meta = self._meta(raw)
            if meta == RELOAD:
                return RELOAD
            if meta == "quit":
                print("中断する。"); sys.exit(0)
            if meta == "handled":
                continue
            if raw.isdigit() and 1 <= int(raw) <= len(labels):
                return labels[int(raw) - 1][0]
            print("  番号で選ぶ（または status / save <名> / load <名> / quit）。")

    def combat_command(self, state, enemies):
        print()
        alive = [e for e in enemies if e.alive]
        print("  ▼ 戦闘 —— " + " / ".join(f"{e.name_ja}(HP{max(0, e.hp)})" for e in alive))
        print(f"     H: HP {state.hp}/{state.hp_max}  MP {state.mp}/{state.mp_max}  薬草 {state.herbs}")
        while True:
            opts = ["attack"]
            if state.mp >= MP_COST:
                opts.append("magic")
            if state.herbs > 0:
                opts.append("herb")
            opts.append("flee")
            print("  コマンド: " + " / ".join(opts))
            raw = input("> ").strip().lower()
            meta = self._meta(raw)
            if meta == RELOAD:
                print("  （戦闘中のロードはこの実装では非対応。安全な選択肢で load を）")
                continue
            if meta == "quit":
                print("中断する。"); sys.exit(0)
            if meta == "handled":
                continue
            if raw in opts:
                return raw
            if raw == "magic" and state.mp < MP_COST:
                print(f"  MP が足りない（{MP_COST} 必要・I-2）。魔法は選べない。")
                continue
            print("  用意されたコマンドから選ぶ。")

    @staticmethod
    def _labels(node, options):
        table = {}
        table.update(dict(FOREST_CHOICES))
        table.update({k: v for k, v in SNEAK_CONTINUE})
        table.update(dict(CAVE_HALL_CHOICES))
        return [(k, table.get(k, k)) for k in options]


def play_interactive(seed: int):
    state = GameState(seed)
    state.respawn_on_defeat = True
    save_dir = os.path.join(LOG_DIR, "saves")
    controller = ConsoleController(state, save_dir)
    print("=" * 60)
    print(f"  Ordia — 決定論 TRPG（seed={seed}・LLM 不使用）")
    print("=" * 60)
    print("村で 3 つ探索する（5 つから）。番号で選ぶ。")
    keys = list_explore_and_pick(controller)
    controller_scripted_explores = keys
    # 探索をコントローラに渡すためのラッパ
    controller.explores = lambda: controller_scripted_explores  # type: ignore
    result = run_session(state, controller)
    print()
    print(node_text("win" if result == "clear" else "defeat"))
    print(f"\n>>> 結果: {result}")
    path = write_log(state)
    print(f">>> ログ: {path}")


def list_explore_and_pick(controller: ConsoleController):
    from .village import EXPLORE, EXPLORE_ORDER
    picked = []
    while len(picked) < 3:
        print(f"\n  ── 探索 {len(picked)+1}/3 ──")
        for i, k in enumerate(EXPLORE_ORDER, 1):
            mark = "（選択済）" if k in picked else ""
            print(f"  {i}) {EXPLORE[k]['name']} — {EXPLORE[k]['gain']} {mark}")
        raw = input("> ").strip()
        meta = controller._meta(raw)
        if meta == "quit":
            sys.exit(0)
        if meta == "handled":
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(EXPLORE_ORDER):
            k = EXPLORE_ORDER[int(raw) - 1]
            if k in picked:
                print("  それは選択済み。")
                continue
            picked.append(k)
            print(f"  → {EXPLORE[k]['text']}")
        else:
            print("  番号で選ぶ。")
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
    ap.add_argument("--replay", action="store_true", help="seed=7 の参照入力列を自動再生してログ出力")
    args = ap.parse_args(argv)

    if args.replay:
        ref = REFERENCE_SEED7
        state = run_scripted(ref["seed"], ref["explores"], ref["node_choices"], ref["combat_cmds"])
        path = write_log(state)
        print(f"replay seed={ref['seed']} → {path}（{len(state.log)} events, ending={state.log[-1].get('result')}）")
        return 0

    play_interactive(args.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
