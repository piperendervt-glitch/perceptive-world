"""resolve.py — 判定エンジン（sdnd-ordia, Step D / D1）.

選択に「やってみないと分からない」を足す。2D6 ＋ 修正値を振り、目標値と比較して
3 段階（＋ゾロ目の特例）で結果を返す。**乱数はコードが独占する**（LLM には振らせない）。

判定基準は Ordia 自前（アリアンロッド等の本文・数表・固有名詞は一切参照しない）。
「2D6 ＋ 修正 ≧ 目標値」という仕組みだけを実装する。2D6 は 7 中心の釣鐘型分布で、
平均が出やすく極端は稀 —— 緩急（[[drama_invariants]] I-D3）と相性が良い。

段階（tier）:
  critical            ゾロ目 6-6。無条件の完全成功・特別な好転。目標値に関わらず。
  full_success        total >= target + MARGIN_BAND。余裕をもって成功、代償なし。
  success_with_cost   target <= total < target + MARGIN_BAND。成功だが代償（I-D5 発火）。
  failure             total < target。失敗。
  fumble              ゾロ目 1-1。無条件の失敗・特別な悪化。目標値に関わらず。

ゾロ目（6-6 / 1-1）は目標値比較より優先される（無条件）。

CLI:
  python resolve.py --modifier 2 --target 8 [--seed 42]
  python resolve.py --regression
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys

# Windows console default cp932 chokes on CJK output; force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 調整可能な定数（Ordia 自前の基準）
# ---------------------------------------------------------------------------

# 「成功だが代償」帯の幅。target <= total < target+MARGIN_BAND を代償ゾーンとする。
# 後で緩急のチューニングに使う（広げれば代償成功が増え、狭めれば白黒がはっきりする）。
MARGIN_BAND = 3

# ゾロ目の定義（各ダイスの面）。6-6=特別な好転、1-1=特別な悪化。
_CRIT_FACE = 6
_FUMBLE_FACE = 1

DICE_COUNT = 2
DICE_SIDES = 6

TIERS = ("critical", "full_success", "success_with_cost", "failure", "fumble")


# ---------------------------------------------------------------------------
# 乱数（コードが独占）
# ---------------------------------------------------------------------------


def _draw_seed() -> int:
    """seed 未指定時に使う再現可能なシードを引く（None のままにしない）。"""
    return random.Random().randrange(2 ** 32)


def roll_dice(rng: random.Random) -> list[int]:
    """2D6 を振る。各出目 1..6。乱数源は呼び出し側が持つ Random インスタンス。"""
    return [rng.randint(1, DICE_SIDES) for _ in range(DICE_COUNT)]


# ---------------------------------------------------------------------------
# 段階判定（純関数：dice と total と target だけで決まる）
# ---------------------------------------------------------------------------


def classify(dice: list[int], total: int, target: int) -> str:
    """dice・total・target から tier を決める。ゾロ目は目標比較より優先。

    純関数（乱数なし）。テスト・境界確認はここを直接叩けばよい。
    """
    if dice[0] == dice[1] == _CRIT_FACE:
        return "critical"
    if dice[0] == dice[1] == _FUMBLE_FACE:
        return "fumble"
    if total >= target + MARGIN_BAND:
        return "full_success"
    if total >= target:
        return "success_with_cost"
    return "failure"


# ---------------------------------------------------------------------------
# 中核関数
# ---------------------------------------------------------------------------


def resolve(modifier: int, target: int, seed: int | None = None) -> dict:
    """2D6 ＋ modifier を振り、target と比較して 3 段階（＋ゾロ目）を返す。

    - modifier: 能力修正（D2 で status から算出。D1 では引数で受ける）。
    - target:   難易度（Adjudicator が決める。D1 では引数で受ける）。
    - seed:     再現用。None なら再現可能なシードを引いて記録する（常に再現可能）。

    返り値（D3 の構造化ログにそのまま載せられる形）:
      {dice, roll_total, modifier, total, target, tier, margin, seed}
    """
    if seed is None:
        seed = _draw_seed()
    rng = random.Random(seed)

    dice = roll_dice(rng)
    roll_total = sum(dice)
    total = roll_total + modifier
    tier = classify(dice, total, target)
    return {
        "dice": dice,
        "roll_total": roll_total,
        "modifier": modifier,
        "total": total,
        "target": target,
        "tier": tier,
        "margin": total - target,
        "seed": seed,
    }


# ---------------------------------------------------------------------------
# ログ構造の器（D3 で拡張。resolve 結果をそのまま入れ子で載せる）
# ---------------------------------------------------------------------------

LOG_SCHEMA_VERSION = 1


def make_log_entry(
    result: dict,
    *,
    actor: str | None = None,
    action: str | None = None,
    adjudicator_note: str | None = None,
) -> dict:
    """resolve() の結果を構造化ログのエンベロープに包む（D3 で拡張予定）.

    D1 では器だけ用意する。予約フィールド:
      actor            : 判定者キャラ（D2 で status 連動）
      action           : 何を試みたか
      adjudicator_note : なぜこの target か（Adjudicator の根拠）
    resolve 結果は "resolve" キーに verbatim で入れる（seed も含む＝再現可能）。
    """
    return {
        "schema_version": LOG_SCHEMA_VERSION,
        "kind": "resolve",
        "actor": actor,
        "action": action,
        "adjudicator_note": adjudicator_note,
        "resolve": result,
    }


# ---------------------------------------------------------------------------
# 回帰（再現性・5 tier の実例・釣鐘型分布）
# ---------------------------------------------------------------------------


def regression() -> int:
    all_ok = True

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        print(f"    [{'OK  ' if ok else 'MISS'}] {name}: {detail}")
        if not ok:
            all_ok = False

    print("===== resolve 回帰（D1）=====")

    # 1) 再現性: 同じ (modifier, target, seed) は同じ結果を返す。
    r1 = resolve(2, 8, seed=42)
    r2 = resolve(2, 8, seed=42)
    check(
        "再現性（seed 固定で同一）",
        r1 == r2,
        f"tier={r1['tier']} dice={r1['dice']} total={r1['total']}（2 回一致={r1 == r2}）",
    )

    # 2) 別 seed は（一般に）別の出目。再現性が「seed に依存」であることの確認。
    seeds_differ = any(
        resolve(0, 8, seed=s)["dice"] != resolve(0, 8, seed=0)["dice"]
        for s in range(1, 10)
    )
    check("seed 依存（別 seed で出目が動く）", seeds_differ, f"differ={seeds_differ}")

    # 3) 純関数 classify の境界（MARGIN_BAND=3, target=8, 非ゾロ目 dice=[3,4]）:
    #    total=7→failure / 8→cost / 10→cost / 11→full。
    nd = [3, 4]  # 非ゾロ目
    bounds = {
        7: "failure",
        8: "success_with_cost",
        10: "success_with_cost",
        11: "full_success",
    }
    bound_ok = all(classify(nd, t, 8) == exp for t, exp in bounds.items())
    check(
        "境界（target=8, band=3）",
        bound_ok,
        ", ".join(f"total{t}->{classify(nd, t, 8)}" for t in sorted(bounds)),
    )

    # 4) ゾロ目は無条件（目標比較を上書き）。
    crit = classify([6, 6], 7, 20)      # total<target でも critical
    fumb = classify([1, 1], 12, 2)      # total>=target でも fumble
    check("ゾロ目 6-6 は無条件 critical", crit == "critical", f"got={crit}（total7<target20）")
    check("ゾロ目 1-1 は無条件 fumble", fumb == "fumble", f"got={fumb}（total12>=target2）")

    # 5) 各 tier の実例を 1 つずつ（実際に seed を振って集める / modifier=0,target=8）。
    found: dict[str, dict] = {}
    for s in range(0, 5000):
        r = resolve(0, 8, seed=s)
        found.setdefault(r["tier"], {**r, "example_seed": s})
        if len(found) == len(TIERS):
            break
    print("    --- 各 tier の実例（modifier=0, target=8, MARGIN_BAND=3）---")
    for tier in TIERS:
        ex = found.get(tier)
        if ex is None:
            check(f"tier 実例 {tier}", False, "見つからず")
            continue
        print(
            f"      {tier:18s} seed={ex['example_seed']:<4d} "
            f"dice={ex['dice']} total={ex['total']} target={ex['target']} "
            f"margin={ex['margin']:+d}"
        )
    check("全 5 tier に実例あり", len(found) == len(TIERS), f"揃った tier={sorted(found)}")

    # 6) 釣鐘型分布: 多数回振って roll_total の最頻値が 7、かつ 7 が両端より多い。
    N = 20000
    rng = random.Random(12345)
    hist = {t: 0 for t in range(2, 13)}
    for _ in range(N):
        d = roll_dice(rng)
        hist[sum(d)] += 1
    mode = max(hist, key=lambda k: hist[k])
    bell_ok = (
        mode == 7
        and hist[7] > hist[2]
        and hist[7] > hist[12]
        and hist[6] > hist[3]
        and hist[8] > hist[11]
    )
    check(
        "2D6 は 7 中心の釣鐘型",
        bell_ok,
        f"mode={mode} 7の数={hist[7]} 2の数={hist[2]} 12の数={hist[12]}",
    )
    print("    --- roll_total 分布（N=%d）---" % N)
    peak = max(hist.values())
    for t in range(2, 13):
        bar = "#" * round(hist[t] / peak * 40)
        print(f"      {t:2d}: {hist[t]:6d} {bar}")

    # 7) ログ器: resolve 結果がそのまま構造化ログに載る。
    entry = make_log_entry(r1, actor="H", action="石の刻印を読む", adjudicator_note="微光で古い刻印=難しめ")
    log_ok = (
        entry["schema_version"] == LOG_SCHEMA_VERSION
        and entry["resolve"] == r1
        and entry["resolve"]["seed"] == 42
    )
    check("構造化ログ器（resolve を verbatim 内包）", log_ok, f"kind={entry['kind']} seed={entry['resolve']['seed']}")

    print()
    print("RESOLVE REGRESSION:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="判定エンジン（2D6＋修正→3段階）D1.")
    ap.add_argument("--modifier", type=int, help="能力修正（D2 で status から算出）")
    ap.add_argument("--target", type=int, help="難易度（Adjudicator が決める）")
    ap.add_argument("--seed", type=int, default=None, help="再現用シード（省略で自動）")
    ap.add_argument("--regression", action="store_true", help="内蔵回帰を実行")
    args = ap.parse_args(argv)

    if args.regression:
        return regression()
    if args.modifier is None or args.target is None:
        ap.error("--modifier と --target が必要（または --regression）")

    result = resolve(args.modifier, args.target, seed=args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
