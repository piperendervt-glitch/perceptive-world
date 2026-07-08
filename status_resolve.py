"""status_resolve.py — 判定のステータス連動（sdnd-ordia, Step D / D2）.

Step A で作った数値（str/mag/vit/MP）を、初めて「見るだけ」から「判定を左右する」に
昇格させる供給層。**D1 の resolve() は無改変**で、その手前に

    行動種別 → 使用能力 → 修正値（modifier）
    魔法的行動 → MP コスト（I-2）→ 消費 / 不足なら試行不可（C-11.1 と整合）

を足す。乱数は依然コードが独占（resolve() が持つ）。判定基準は Ordia 自前で、
アリアンロッド等の本文・数表・固有名詞は一切参照しない。

不変条件との接続:
  I-2  魔法のコスト  : 魔法的判定は MP を消費する。消費なしに発動しない。
  I-3  血統と地位    : mag は血統に相関。血統のない転生者 H は mag が伸びず、
                       魔法判定の modifier が低い＝不利。この不利が数値として効く。
  C-11.1 requires   : MP 不足なら判定を試みられない（Step B の requires 判定と同じ論理）。

CLI:
  python status_resolve.py --action magic --char H --target 9 [--seed 42]
  python status_resolve.py --regression
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from resolve import make_log_entry, resolve

# Windows console default cp932 chokes on CJK output; force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 行動種別 → 使用能力の対応（Ordia 自前の対応表）
# ---------------------------------------------------------------------------
#
# status.yaml が持つ属性は str / mag / vit の 3 種。行動種別はこの 3 つへ写像する。
# 「身体的判定 → str または vit」は force（力技）と endure（耐久）に分けて表現する。

ACTION_ABILITY: dict[str, str] = {
    "magic":  "mag",   # 魔法的判定 —— 詠唱・術式・感応（血統相関 I-3 の効く軸）
    "force":  "str",   # 力技       —— 押す・殴る・こじ開ける・担ぐ
    "endure": "vit",   # 耐久       —— 毒・寒暑・痛み・恐怖に耐える／粘る
}

# MP（自己資源 I-2）を要する行動種別。ここに載る行動だけが MP を消費する。
MAGIC_ACTIONS: frozenset[str] = frozenset({"magic"})


# ---------------------------------------------------------------------------
# 調整可能な定数（Ordia 自前の基準）
# ---------------------------------------------------------------------------

# 能力値を modifier に写す基準点。8 = status.yaml が言う「血統補正なしの一般人相当」。
# 一般人は ±0、鍛錬や血統で基準から乖離した分だけが判定に効く。
#   modifier = attribute - ABILITY_PIVOT
# 血統のない H は mag=8 → 魔法 modifier 0。血統持ちは mag が上振れ → 正の modifier。
# この差が I-3（血統相関）を数値として判定に載せる。
ABILITY_PIVOT = 8

# 魔法的判定の既定 MP コスト（I-2）。呪文の規模による可変化は将来（引数で上書き可能）。
MAGIC_MP_COST = 2

# MP 現在値の在り処（status.yaml の mp: {cur, max}）。Step A/B の delta と同じ経路。
_MP_PATH = ("mp", "cur")


# ---------------------------------------------------------------------------
# 対応表・modifier の算出
# ---------------------------------------------------------------------------


def ability_for_action(action_type: str) -> str:
    """行動種別から使用能力（str/mag/vit）を引く。未知の行動種別は例外。"""
    try:
        return ACTION_ABILITY[action_type]
    except KeyError:
        raise ValueError(
            f"未知の action_type={action_type!r}。"
            f"定義済み: {sorted(ACTION_ABILITY)}"
        ) from None


def is_magic_action(action_type: str) -> bool:
    """MP（I-2）を要する魔法的行動か。"""
    return action_type in MAGIC_ACTIONS


def _char_status(char: str, status: dict) -> dict:
    c = status.get("characters", {}).get(char)
    if c is None:
        known = sorted(status.get("characters", {}))
        raise ValueError(f"未知のキャラ char={char!r}。既知: {known}")
    return c


def modifier_from_status(action_type: str, char: str, status: dict) -> int:
    """使用能力値から modifier を算出する（純関数・乱数なし）。

    modifier = attribute - ABILITY_PIVOT
    D1 の resolve(modifier, target) に「供給」する値。resolve は無改変。
    """
    ability = ability_for_action(action_type)
    c = _char_status(char, status)
    attrs = c.get("attributes", {})
    if ability not in attrs:
        raise ValueError(
            f"char={char} に能力 {ability!r} がない（attributes={sorted(attrs)}）"
        )
    return int(attrs[ability]) - ABILITY_PIVOT


def mp_cost_for(action_type: str, override: int | None = None) -> int:
    """行動種別の MP コスト。魔法的行動のみ正の値。override で上書き可能。"""
    if not is_magic_action(action_type):
        return 0
    return MAGIC_MP_COST if override is None else int(override)


def magic_requires(action_type: str, mp_cost: int | None = None) -> dict:
    """魔法的判定をゲートする decision.option.requires を作る（C-11.1 と同形式）。

    決定点でこの判定を選択肢にするとき、この requires を載せれば C-11.1 が
    MP 不足を Major で弾く。resolve_action 側の弾きと同じ論理を共有する。
    """
    cost = mp_cost_for(action_type, mp_cost)
    return {"mp": cost} if cost > 0 else {}


# ---------------------------------------------------------------------------
# 供給層：status から modifier / MP を供給して resolve() を回す
# ---------------------------------------------------------------------------


def resolve_action(
    action_type: str,
    char: str,
    target: int,
    status: dict,
    *,
    seed: int | None = None,
    mp_cost: int | None = None,
) -> dict:
    """行動種別＋キャラ status から判定を実行する（D2 の入口）。

    手順:
      1. action_type → 使用能力 → modifier（modifier_from_status）。
      2. 魔法的行動なら MP コストを引き、現在 MP が足りるか確認。
         足りなければ **試行しない**（attempted=False, blocked=insufficient_mp）。
         これは Step B の C-11.1（requires:{mp} を満たせるか）と同じ判定。
      3. 足りる（または非魔法）なら D1 の resolve(modifier, target, seed) を回す。
         魔法なら MP delta を添える（Step A/B の delta 機構を再利用。適用は editor）。

    返り値（make_log_entry にそのまま入れ子で載せられる）:
      {action_type, char, ability, modifier, target, is_magic, mp_cost,
       mp_before, mp_after?, requires, attempted, blocked?, status_delta?, resolve}
    """
    ability = ability_for_action(action_type)
    modifier = modifier_from_status(action_type, char, status)
    c = _char_status(char, status)
    magic = is_magic_action(action_type)
    cost = mp_cost_for(action_type, mp_cost)

    out: dict = {
        "action_type": action_type,
        "char": char,
        "ability": ability,
        "modifier": modifier,
        "target": target,
        "is_magic": magic,
        "mp_cost": cost,
        "requires": magic_requires(action_type, mp_cost),
    }

    if magic:
        mp_before = int(c.get("mp", {}).get("cur", 0))
        out["mp_before"] = mp_before
        if mp_before < cost:
            # C-11.1 と整合：requires:{mp: cost} を満たせない → 試行不可。乱数を振らない。
            out["attempted"] = False
            out["blocked"] = "insufficient_mp"
            out["resolve"] = None
            return out
        out["mp_after"] = mp_before - cost
        # Step A/B の delta 形式（editor が canon に適用する）。cause は I-2 由来を明示。
        out["status_delta"] = [
            {"char": char, "change": {"mp.cur": -cost}, "cause": f"魔法発動 (I-2, {action_type})"}
        ]

    out["attempted"] = True
    out["resolve"] = resolve(modifier, target, seed=seed)
    return out


# ---------------------------------------------------------------------------
# status の読み込み
# ---------------------------------------------------------------------------


def load_status(path: str | Path = "canon/status.yaml") -> dict:
    if yaml is None:  # pragma: no cover
        raise RuntimeError("pyyaml が必要です（pip install pyyaml）。")
    text = Path(path).read_text(encoding="utf-8")
    return yaml.safe_load(text) or {}


# ---------------------------------------------------------------------------
# 回帰（modifier 算出・MP 不足の弾き・数値の単調性・I-3 整合）
# ---------------------------------------------------------------------------

# tier を「成功寄りかどうか」で順位づけ（数値が判定を左右する証拠の確認に使う）。
# ゾロ目（critical/fumble）は無条件特例なので単調性テストからは除外する。
_TIER_RANK = {"failure": 0, "success_with_cost": 1, "full_success": 2}


def regression(status_path: str = "canon/status.yaml") -> int:
    all_ok = True

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        print(f"    [{'OK  ' if ok else 'MISS'}] {name}: {detail}")
        if not ok:
            all_ok = False

    print("===== status 連動 回帰（D2）=====")
    status = load_status(status_path)
    H = status["characters"]["H"]
    print(
        f"    H の status: attributes={H['attributes']} "
        f"mp={H['mp']} (blood: 血統補正なし=commoner, I-3)"
    )

    # 1) 対応表: 行動種別 → 使用能力。
    map_ok = (
        ability_for_action("magic") == "mag"
        and ability_for_action("force") == "str"
        and ability_for_action("endure") == "vit"
    )
    check("行動種別→能力の対応", map_ok, str(ACTION_ABILITY))

    # 2) modifier 算出: H の各能力から（attribute - PIVOT(=8)）。
    m_mag = modifier_from_status("magic", "H", status)
    m_force = modifier_from_status("force", "H", status)
    m_endure = modifier_from_status("endure", "H", status)
    mod_ok = (
        m_mag == H["attributes"]["mag"] - ABILITY_PIVOT
        and m_force == H["attributes"]["str"] - ABILITY_PIVOT
        and m_endure == H["attributes"]["vit"] - ABILITY_PIVOT
    )
    check(
        "modifier 算出（attr - PIVOT）",
        mod_ok,
        f"magic(mag8)->{m_mag:+d}, force(str8)->{m_force:+d}, endure(vit9)->{m_endure:+d}",
    )

    # 3) I-3 整合: 血統のない H の mag は基準 → 魔法 modifier=0。
    #    血統持ち（合成: mag を上げた仮想キャラ）は正の modifier。H は相対的に不利。
    blooded = copy.deepcopy(status)
    blooded["characters"]["H"]["attributes"]["mag"] = 13  # 血統持ち相当（合成・canon 非書込）
    m_blood = modifier_from_status("magic", "H", blooded)
    i3_ok = m_mag == 0 and m_blood > m_mag
    check(
        "I-3 血統相関（H は魔法不利）",
        i3_ok,
        f"H mag8->modifier {m_mag:+d} / 血統持ち mag13->modifier {m_blood:+d}（差 {m_blood - m_mag:+d}）",
    )

    # 4) 魔法判定は MP を消費（I-2）。H(mp.cur=2, cost=2)は 1 回撃てて mp→0。
    r_cast = resolve_action("magic", "H", target=9, status=status, seed=7)
    cast_ok = (
        r_cast["is_magic"]
        and r_cast["attempted"]
        and r_cast["mp_cost"] == MAGIC_MP_COST
        and r_cast["mp_before"] == 2
        and r_cast["mp_after"] == 0
        and r_cast["status_delta"] == [
            {"char": "H", "change": {"mp.cur": -2}, "cause": "魔法発動 (I-2, magic)"}
        ]
        and r_cast["resolve"]["modifier"] == 0
    )
    check(
        "魔法判定は MP 消費（I-2）",
        cast_ok,
        f"mp {r_cast['mp_before']}->{r_cast['mp_after']}, "
        f"delta={r_cast['status_delta']}, tier={r_cast['resolve']['tier']}",
    )

    # 5) MP 不足なら試行不可（C-11.1 と整合）。H の mp を 1 に下げて魔法（cost=2）を試みる。
    low = copy.deepcopy(status)
    low["characters"]["H"]["mp"]["cur"] = 1
    r_block = resolve_action("magic", "H", target=9, status=low, seed=7)
    block_ok = (
        r_block["attempted"] is False
        and r_block["blocked"] == "insufficient_mp"
        and r_block["resolve"] is None
        and r_block["requires"] == {"mp": 2}
    )
    check(
        "MP 不足で魔法判定を弾く（C-11.1 整合）",
        block_ok,
        f"mp_before={r_block['mp_before']} cost={r_block['mp_cost']} "
        f"blocked={r_block.get('blocked')} requires={r_block['requires']}",
    )

    # 6) 非魔法（force）は MP を消費しない。
    r_force = resolve_action("force", "H", target=9, status=status, seed=7)
    force_ok = (
        r_force["is_magic"] is False
        and r_force["mp_cost"] == 0
        and "status_delta" not in r_force
        and r_force["attempted"]
        and r_force["resolve"]["modifier"] == m_force
    )
    check(
        "非魔法（force）は MP 非消費",
        force_ok,
        f"mp_cost={r_force['mp_cost']} modifier={r_force['resolve']['modifier']:+d}",
    )

    # 7) 数値が判定を左右する（単調性）: 同 seed・同 target で、mag が高いほど
    #    tier は「成功寄り」に等しいか上（ゾロ目は特例なので除外）。
    #    H(mag8, mod0) と 血統持ち(mag13, mod+5) を多数の (seed,target) で比較。
    mono_ok = True
    counter = ""
    improved = 0
    compared = 0
    for seed in range(0, 200):
        for target in (7, 9, 11):
            lo = resolve_action("magic", "H", target=target, status=status, seed=seed)
            hi = resolve_action("magic", "H", target=target, status=blooded, seed=seed)
            lt, ht = lo["resolve"]["tier"], hi["resolve"]["tier"]
            if lt not in _TIER_RANK or ht not in _TIER_RANK:
                continue  # ゾロ目（同 seed なら両者同じ出目なので同時に除外される）
            compared += 1
            if _TIER_RANK[ht] < _TIER_RANK[lo["resolve"]["tier"]]:
                mono_ok = False
                counter = f"seed={seed} target={target}: low={lt} high={ht}"
                break
            if _TIER_RANK[ht] > _TIER_RANK[lt]:
                improved += 1
        if not mono_ok:
            break
    check(
        "数値が判定を左右（mag 高いほど成功寄り）",
        mono_ok and improved > 0,
        (f"反例 {counter}" if not mono_ok
         else f"比較 {compared} 件中 {improved} 件で高 mag が上位 tier、逆転 0"),
    )

    # 8) resolve は無改変で使えている（供給層は resolve 結果を verbatim 内包）。
    #    make_log_entry にそのまま載る（D3 で拡張）。
    entry = make_log_entry(
        r_cast["resolve"], actor="H", action="magic", adjudicator_note="D2 供給層経由"
    )
    log_ok = entry["resolve"] == r_cast["resolve"] and entry["resolve"]["seed"] is not None
    check("resolve 無改変・ログ器に載る", log_ok, f"seed={entry['resolve']['seed']}")

    print()
    print("STATUS-RESOLVE REGRESSION:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="判定のステータス連動（行動種別→modifier→resolve, 魔法はMP消費）D2."
    )
    ap.add_argument("--action", choices=sorted(ACTION_ABILITY), help="行動種別")
    ap.add_argument("--char", default="H", help="判定するキャラ（既定 H）")
    ap.add_argument("--target", type=int, help="難易度（Adjudicator が決める）")
    ap.add_argument("--seed", type=int, default=None, help="再現用シード（省略で自動）")
    ap.add_argument("--mp-cost", type=int, default=None, help="魔法の MP コスト上書き")
    ap.add_argument("--status", default="canon/status.yaml", help="status.yaml のパス")
    ap.add_argument("--regression", action="store_true", help="内蔵回帰を実行")
    args = ap.parse_args(argv)

    if args.regression:
        return regression(args.status)
    if args.action is None or args.target is None:
        ap.error("--action と --target が必要（または --regression）")

    status = load_status(args.status)
    result = resolve_action(
        args.action, args.char, args.target, status,
        seed=args.seed, mp_cost=args.mp_cost,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
