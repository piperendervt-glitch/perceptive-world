"""rules.py — 判定・修正値・定数（成否二択）.

resolve.py（D1）は 2D6→3 段階の物語判定だが、この engine は普通の TRPG として
**成否二択**を使う（下記 roll）。同じ mulberry32 の乱数を 2 回引いて 2D6 とする。

判定式:
    roll(rng, modifier, target):
        dice = [d6(), d6()]
        sum   = dice[0] + dice[1]
        total = sum + modifier
        crit   = (sum == 12)   # 6-6 → 自動成功
        fumble = (sum == 2)    # 1-1 → 自動失敗
        success = crit or (not fumble and total >= target)
"""

from __future__ import annotations

from .rng import Rng, d6

# --- 判定の仕組み（エンジン側の定数）。キャラの能力値そのものはシナリオが持つ。 ---
PIVOT = 8       # 能力値の基準（血統補正なしの一般人相当）= modifier ±0
MP_COST = 2     # I-2: 魔法 1 回のコスト


def modifier(attribute: int) -> int:
    """能力値 → 修正値。attribute - PIVOT（str+0 / mag+0 / vit+1 が既定）。"""
    return attribute - PIVOT


# ---------------------------------------------------------------------------
# 効果(effect)の適用ロジック（★エンジン側）
#   宣言はシナリオ(YAML)、解釈と適用はここ。state.effects は受動効果の宣言リスト
#   （item は探索時に state.herbs へ畳み込むので、ここには hit_bonus/damage_bonus/
#   recon だけが積まれる）。新しい effect.type を足すときだけエンジンを触る。
# ---------------------------------------------------------------------------

def effect_hit_bonus(state, target_key: str) -> int:
    """命中への上乗せ。target_enemy 指定なし＝全対象、指定あり＝その敵のみ。
    （祝福 value1・全対象 / 村長 value2・頭目のみ、を一般化して合算）。"""
    total = 0
    for eff in state.effects:
        if eff.get("type") != "hit_bonus":
            continue
        te = eff.get("target_enemy")
        if te is None or te == target_key:
            total += int(eff.get("value", 0))
    return total


def effect_damage_bonus(state, kind: str) -> int:
    """ダメージへの上乗せ（kind が一致するものだけ）。短剣 physical+2 を一般化。"""
    total = 0
    for eff in state.effects:
        if eff.get("type") == "damage_bonus" and eff.get("kind") == kind:
            total += int(eff.get("value", 0))
    return total


def has_recon(state) -> bool:
    """偵察効果を持つか（藪自動成功・忍び補正・初撃必中の可否）。"""
    return any(eff.get("type") == "recon" for eff in state.effects)


def roll(rng: Rng, mod: int, target: int) -> dict:
    """2D6 + mod を振り、target と比較。成否二択（＋ゾロ目の特例）。

    返り値: {dice, sum, modifier, total, target, crit, fumble, success}
    乱数は d6 を 2 回だけ消費する（呼び出し順が seed 直結）。
    """
    dice = [d6(rng), d6(rng)]
    s = dice[0] + dice[1]
    total = s + mod
    crit = s == 12
    fumble = s == 2
    success = True if crit else (False if fumble else total >= target)
    return {
        "dice": dice,
        "sum": s,
        "modifier": mod,
        "total": total,
        "target": target,
        "crit": crit,
        "fumble": fumble,
        "success": success,
    }
