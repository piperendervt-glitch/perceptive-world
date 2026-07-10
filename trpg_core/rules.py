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

# --- キャラクター（Ordia の H）: canon/status.yaml が読めれば max 値を使い、
#     読めなければ以下でフォールバックする（session.load_character が実施） ---
PIVOT = 8       # 能力値の基準（血統補正なしの一般人相当）= modifier ±0
MP_COST = 2     # I-2: 魔法 1 回のコスト

DEFAULT_CHAR = {
    "hp_max": 20,
    "mp_max": 10,
    "str": 8,
    "mag": 8,
    "vit": 9,
}


def modifier(attribute: int) -> int:
    """能力値 → 修正値。attribute - PIVOT（str+0 / mag+0 / vit+1 が既定）。"""
    return attribute - PIVOT


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
