"""combat.py — 戦闘（成否二択・敵ターン・ターンカウンタ規律）.

行動:
  attack : 命中判定 vs player_target → d6 + mod(str) + (短剣?2:0)、最低 1、会心で ×2
  magic  : MP を 2 消費(I-2)。MP 不足なら選べない。命中判定 → d6 + 3 + mod(mag)、最低 1、会心 ×2
  herb   : 薬草を 1 消費。d6 + 3 回復。**このターンも敵は攻撃する**
  flee   : roll(mod(vit), 8) 成功で forest へ離脱。失敗なら敵の攻撃を受ける

敵ターン: 生存している敵が全員、配列順に roll(atk, 8) →成功で dmg_lo + floor(next*(幅)) のダメージ。
攻撃対象: 生存している敵のうち最初の 1 体（配列順）。
偵察の必中: cave_entrance の**最初の 1 回の攻撃のみ**、判定せず自動命中（ダメージの d6 は振る）。
HP 0 → 敗北（死なない。村で目覚め、HP 半分回復・MP 全快、再挑戦可）。

★ターンカウンタ規律（参照ログと一致させる要）:
  各ラウンドの開始時の turn を base とし、ラウンドの全イベントを最終 turn で刻印する。
    - 勝利したラウンド（このラウンドで敵が全滅）: turn = base + 2
    - それ以外のラウンド（離脱・敗北・継続）    : turn = base + 1
  encounter はノード進入時の turn（＝ base の直前）で記録する。
"""

from __future__ import annotations

from .enemies import make_group
from .rules import MP_COST, modifier, roll
from .rng import d6
from .scenario import COMBAT_ENEMIES, FLEE_TARGET

ENEMY_ATTACK_TARGET = 8  # 敵の命中目標値


def _first_alive(enemies):
    for e in enemies:
        if e.alive:
            return e
    return None


def _hit_bonus(state, target) -> int:
    """命中への上乗せ（祝福・村長）。damage には乗らない（命中のみ）。"""
    bonus = 1 if state.blessing else 0
    if state.elder and target.key == "chief":
        bonus += 2
    return bonus


def run_combat(state, node: str, controller, first_free_hit: bool = False) -> str:
    """1 戦闘を最後まで回す。戻り値: "win" / "defeat" / "fled"。"""
    enemies = make_group(COMBAT_ENEMIES[node])
    state.emit(type="encounter", node=node, enemies=[e.key for e in enemies])
    free_hit = first_free_hit

    while True:
        base = state.turn
        events: list[dict] = []
        outcome = None  # "win"/"defeat"/"fled"/None(継続)

        cmd = controller.combat_command(state, enemies)
        # --- 合法化: MP 不足で magic は選べない(I-2/C-11.1)、薬草切れで herb は選べない ---
        if cmd == "magic" and state.mp < MP_COST:
            cmd = "attack"
        if cmd == "herb" and state.herbs <= 0:
            cmd = "attack"

        if cmd == "flee":
            rr = roll(state.rng, modifier(state.vit), FLEE_TARGET)
            events.append({"type": "check", "tag": "flee", **rr})
            if rr["success"]:
                outcome = "fled"
            # 失敗時は下の敵ターンで攻撃を受ける

        elif cmd == "herb":
            heal = d6(state.rng) + 3
            state.herbs -= 1
            state.hp = min(state.hp_max, state.hp + heal)
            events.append({"type": "herb", "heal": heal, "hp": state.hp, "herbs": state.herbs})
            # このターンも敵は攻撃する（下の敵ターンへ）

        else:  # attack / magic（攻撃行動）
            kind = cmd
            target = _first_alive(enemies)
            if kind == "magic":
                state.mp -= MP_COST
                events.append({
                    "type": "mp_cost", "cost": MP_COST, "mp": state.mp,
                    "cause": "魔法発動 (I-2)",
                })
                base_ability = state.mag
            else:
                base_ability = state.str

            hitmod = modifier(base_ability) + _hit_bonus(state, target)

            if free_hit:
                free_hit = False
                events.append({"type": "check", "tag": "free_hit", "auto": True, "success": True})
                hit, crit, fumble = True, False, False
            else:
                rr = roll(state.rng, hitmod, target.player_target)
                events.append({"type": "check", "tag": f"{kind}_attack", **rr})
                hit, crit, fumble = rr["success"], rr["crit"], rr["fumble"]

            if hit:
                if kind == "magic":
                    dmg = d6(state.rng) + 3 + modifier(state.mag)
                else:
                    dmg = d6(state.rng) + modifier(state.str) + (2 if state.dagger else 0)
                if crit:
                    dmg *= 2
                dmg = max(1, dmg)
                target.hp -= dmg
                events.append({
                    "type": "player_attack", "kind": kind, "target": target.key,
                    "damage": dmg, "crit": crit, "enemy_hp": max(0, target.hp),
                })
            else:
                events.append({
                    "type": "player_attack", "kind": kind, "target": target.key,
                    "damage": 0, "fumble": fumble,
                })

            if all(not e.alive for e in enemies):
                outcome = "win"

        # --- 敵ターン（勝利・離脱でない限り、生存する敵が配列順に攻撃） ---
        if outcome is None:
            for e in enemies:
                if not e.alive:
                    continue
                rr = roll(state.rng, e.atk, ENEMY_ATTACK_TARGET)
                hit = rr["success"]
                dmg = 0
                if hit:
                    span = e.dmg_hi - e.dmg_lo + 1
                    dmg = e.dmg_lo + int(state.rng.next() * span)
                    state.hp -= dmg
                events.append({
                    "type": "enemy_attack", "enemy": e.key, "dice": rr["dice"],
                    "total": rr["total"], "hit": hit, "damage": dmg,
                    "player_hp": max(0, state.hp),
                })
                if state.hp <= 0:
                    outcome = "defeat"
                    break

        # --- ターンカウンタ確定 → 刻印して emit ---
        state.turn = base + (2 if outcome == "win" else 1)
        for ev in events:
            state.emit(**ev)

        if outcome == "win":
            state.emit(type="combat_win", node=node)
            return "win"
        if outcome == "defeat":
            state.emit(type="defeat", node=node)
            return "defeat"
        if outcome == "fled":
            return "fled"
        # 継続: 次のラウンドへ
