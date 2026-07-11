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
from .rules import MP_COST, modifier, roll, has_recon
from .scenario_loader import load_scenario

# Windows console default cp932 chokes on CJK output; force UTF-8（resolve.py と同流儀）。
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
RELOAD = "__reload__"
DEFAULT_SCENARIO = "goblin"


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
        self.started = False
        self.respawn_on_defeat = False
        self.log: list[dict] = []
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

    def reset_for_village(self) -> None:
        """敗北後の再起（Fix3）: HP/MP を全快し、授かり・薬草をリセットする。
        探索フェーズをやり直すため、一度きりの探索ボーナスも白紙に戻す。
        seed/rng/turn/log/hp_max などの進行・再現要素は保持する。"""
        self.hp = self.hp_max
        self.mp = self.mp_max
        self.effects = []
        self.herbs = 0
        self.buff_labels = []

    # --- save/load（★rng の内部状態 a を含む＝ロード後の乱数列が一致する） ---
    _SNAP_FIELDS = (
        "seed", "hp_max", "mp_max", "hp", "mp", "str", "mag", "vit",
        "effects", "herbs", "buff_labels",
        "turn", "node", "started", "respawn_on_defeat",
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
    state.node = node_id
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
        state.reset_for_village()
        state.emit(type="respawn", hp=state.hp, mp=state.mp)
        _run_village(state, controller)      # 探索を選び直す（on_defeat_return: village）
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

    def __init__(self, state: GameState, save_dir: str):
        self.state = state
        self.save_dir = save_dir
        # 判定結果・敵ターン・敗北描写を「起きた順」に画面へ出す（表示専用フック）。
        state.presenter = self.present_event

    # --- 探索フェーズ（対話・敗北後もここに戻る＝Fix3） ---
    def explores(self):
        sc = self.state.scenario
        print()
        print(f"  ── 支度 —— 出立の前に、{len(sc.village_order)} つから {sc.village_pick_count} つ選ぶ ──")
        return list_explore_and_pick(self)

    # --- 判定・戦闘の結果表示（Fix1）／敗北描写（Fix2） ---
    #     ここは state.log から読む「表示層」。ログ・乱数・判定には一切触れない。
    def present_event(self, ev: dict) -> None:
        t = ev.get("type")
        if t == "encounter":
            self._show_encounter(ev)
        elif t == "check":
            self._show_check(ev)
        elif t == "mp_cost":
            print(f"     魔力を {ev['cost']} 消費（残 MP {ev['mp']}）")
        elif t == "player_attack":
            self._show_player_attack(ev)
        elif t == "enemy_attack":
            self._show_enemy_attack(ev)
        elif t == "herb":
            print(f"     薬草を噛む —— HP+{ev['heal']}（HP {ev['hp']}／残 薬草 {ev['herbs']}）")
        elif t == "combat_win":
            print("     ——敵を退けた。")
        elif t == "defeat":
            print()
            print("  H は膝から崩れ落ちた。意識が遠のく——")
        elif t == "respawn":
            print()
            print("  気がつくと、村の広場に寝かされていた。誰かが運んでくれたらしい。")
            print("  傷は洗われ、息は整っている。だが、支度は最初からやり直しだ。")
            print("  ——まだ、終わってはいない。もう一度、森へ。")

    def _show_encounter(self, ev):
        sc = self.state.scenario
        print()
        txt = sc.node_text(ev["node"])
        if txt:
            print(f"  {txt}")
        names = "／".join(sc.enemy_name(k) for k in ev["enemies"])
        print(f"  ▼ 戦闘 —— {names}")

    def _show_check(self, ev):
        tag = ev.get("tag")
        label = {
            "sneak": "藪を抜ける〔vit〕",
            "vit_check": "松明を消して忍ぶ〔vit〕",
            "flee": "離脱をはかる〔vit〕",
            "free_hit": "偵察の一手",
            "attack_attack": "H の斬撃〔str〕",
            "magic_attack": "H の呪〔mag〕",
        }.get(tag, tag or "判定")
        # 成否の語を判定種別に合わせる
        if tag in ("attack_attack", "magic_attack", "free_hit"):
            ok, ng = "命中", "外れ"
        elif tag == "flee":
            ok, ng = "振り切った", "逃げ損ねた"
        else:
            ok, ng = "成功", "失敗"
        if ev.get("auto"):
            print(f"     {label} —— {ok}（自動）")
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
        print(f"     {label}: 2D6[{dice[0]},{dice[1]}]={ev['sum']} {sign} "
              f"→ {ev['total']} vs 目標{ev['target']} → {result}")

    def _show_player_attack(self, ev):
        if ev.get("damage", 0) > 0:
            crit = "（会心！）" if ev.get("crit") else ""
            print(f"     → {self.state.scenario.enemy_name(ev['target'])} に {ev['damage']} ダメージ{crit}"
                  f"（残 HP {ev['enemy_hp']}）")
        # 外れは check 行が「外れ」と出しているので、ここでは重ねない。

    def _show_enemy_attack(self, ev):
        d = ev["dice"]
        name = self.state.scenario.enemy_name(ev["enemy"])
        if ev["hit"]:
            print(f"     {name} の攻撃 [{d[0]},{d[1]}]={ev['total']} "
                  f"→ {ev['damage']} ダメージを受けた（HP {ev['player_hp']}）")
        else:
            print(f"     {name} の攻撃 [{d[0]},{d[1]}]={ev['total']} → かわした")

    # --- 内心表示（I-4: H にだけ見えているもの） ---
    def _show_status(self):
        s = self.state
        print("  ── H の内心（転生者にだけ見える数値・I-4）──")
        print(f"     HP {s.hp}/{s.hp_max}   MP {s.mp}/{s.mp_max}   薬草 {s.herbs}")
        print(f"     str {s.str}(+{modifier(s.str)})  mag {s.mag}(+{modifier(s.mag)})  vit {s.vit}(+{modifier(s.vit)})")
        print(f"     授かり: {', '.join(s.buff_labels) if s.buff_labels else 'なし'}")

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
        sc = self.state.scenario
        n = sc.node(node)
        print()
        txt = sc.node_text(node)
        if txt:
            print(txt)
        labels = [(c.key, c.label) for c in n.choices]
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


def play_interactive(seed: int, scenario_id: str = DEFAULT_SCENARIO):
    scenario = load_scenario(scenario_id)
    state = GameState(seed, scenario=scenario)
    state.respawn_on_defeat = True
    save_dir = os.path.join(LOG_DIR, "saves")
    controller = ConsoleController(state, save_dir)  # ← ここで presenter を装着
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
        print(f"\n  ── 支度 {len(picked)+1}/{pick_count} ──")
        for i, key in enumerate(order, 1):
            opt = sc.village_option(key)
            mark = "（選択済）" if key in picked else ""
            print(f"  {i}) {opt['name']} — {opt.get('gain', '')} {mark}")
        raw = input("> ").strip()
        meta = controller._meta(raw)
        if meta == "quit":
            sys.exit(0)
        if meta == "handled":
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(order):
            key = order[int(raw) - 1]
            if key in picked:
                print("  それは選択済み。")
                continue
            picked.append(key)
            print(f"  → {sc.village_option(key).get('text', '')}")
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
    ap.add_argument("--scenario", default=DEFAULT_SCENARIO,
                    help="scenarios/<id>.yaml を選ぶ（既定: goblin）")
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

    play_interactive(args.seed, scenario_id=args.scenario)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
