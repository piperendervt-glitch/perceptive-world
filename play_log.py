"""play_log.py — 出目表示モード・tier 帰結・構造化ログ（sdnd-ordia, Step D / D3）.

D1（resolve）・D2（status 連動）で出た判定結果を、

  1. **出目表示モード** reveal_dice で「見せる／隠す」を切り替えて player に提示し、
  2. tier の帰結（success_with_cost=I-D5 の代償）を writer が物語として描くための素材にし、
  3. **動画化を見据えた構造化ログ** `meta/play_log.yaml` に機械可読で残す。

方針:
  - reveal_dice の既定は **true（表示）**。false は当初構想の「隠しモード」。
  - **出目非表示モードでも、ログには出目を残す**（内部真実は常に保持）。
  - D1 の器 `make_log_entry` を実運用に接続する（resolve を verbatim 内包）。
  - 動画機能そのものは作らない。ここは「素材化」まで。

CLI:
  python play_log.py --regression
  python play_log.py --demo --seed 3          # 提示の見え方を表示（reveal 両モード）
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from resolve import make_log_entry


class _NoAliasDumper(getattr(yaml, "SafeDumper", object) if yaml else object):
    """アンカー/エイリアス（&id / *id）を出さない。動画側の素朴なパーサ向けに、
    同一オブジェクト参照でも値を展開して書く。"""

    def ignore_aliases(self, data):  # noqa: D401
        return True


def _dump(data) -> str:
    return yaml.dump(
        data, Dumper=_NoAliasDumper, allow_unicode=True,
        sort_keys=False, default_flow_style=False,
    )


# Windows console default cp932 chokes on CJK output; force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 出目表示モード
# ---------------------------------------------------------------------------

# 既定は表示（普通の TRPG）。false は結果の物語だけ見せ、出目は内部ログのみ。
DEFAULT_REVEAL_DICE = True


def load_reveal_dice(config_path: str | Path = "config/play.yaml") -> bool:
    """config/play.yaml の reveal_dice を読む。無ければ既定（true）。"""
    p = Path(config_path)
    if yaml is None or not p.exists():  # pragma: no cover
        return DEFAULT_REVEAL_DICE
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    val = data.get("reveal_dice", DEFAULT_REVEAL_DICE)
    return bool(val)


# ---------------------------------------------------------------------------
# tier の帰結（writer が物語として描くための「形」）
# ---------------------------------------------------------------------------
#
# writer はここで示す「帰結の形」を散文に翻訳する（数値の再掲ではない）。
# success_with_cost は必ず I-D5（得た＝失った）を織る。曖昧さは明瞭さ規律 I-D8/I-D9 に従う。

TIER_OUTCOME: dict[str, str] = {
    "critical":          "望み以上の好転（特別な幸運）。代償なし、さらに一歩得る。",
    "full_success":      "望みが叶う。代償なし。",
    "success_with_cost": "叶うが代償・複雑化を伴う（I-D5：得た＝失った を織る）。",
    "failure":           "叶わず、状況が悪化する（Director の燃料）。",
    "fumble":            "特別な悪化。ただ失敗する以上の綻びが生まれる。",
}

# I-D5（得た＝失った）が発火する tier。success_with_cost が本則。
_ID5_TIER = "success_with_cost"


# ---------------------------------------------------------------------------
# player 提示（reveal_dice で見え方が変わる／ログは別で常に完全）
# ---------------------------------------------------------------------------


def present_result(action_result: dict, *, reveal_dice: bool = DEFAULT_REVEAL_DICE) -> dict:
    """判定結果を player 向けの見え方に整形する。ログ（完全）はここでは作らない。

    - attempted=False（MP 不足等で試行不可, C-11.1）: 出目は無い。弾かれた事実だけ。
    - reveal_dice=True : dice / total / target / tier を提示（普通の TRPG）。
    - reveal_dice=False: tier の帰結（物語の形）だけ提示。出目は隠す（内部ログのみ）。
    """
    r = action_result
    if not r.get("attempted", True):
        return {
            "reveal_dice": reveal_dice,
            "attempted": False,
            "shown_to_player": {
                "outcome": "資源不足で行動を試みられない（C-11.1 と整合）",
                "reason": r.get("blocked"),
            },
        }

    res = r["resolve"]
    tier = res["tier"]
    if reveal_dice:
        shown = {
            "dice": res["dice"],
            "roll_total": res["roll_total"],
            "modifier": res["modifier"],
            "total": res["total"],
            "target": res["target"],
            "tier": tier,
            "line": (
                f"2D6{res['dice']}={res['roll_total']} "
                f"{res['modifier']:+d} → {res['total']} vs 目標{res['target']} … {tier}"
            ),
        }
    else:
        # 隠しモード：出目・目標・tier ラベルは伏せ、帰結の「形」だけを渡す。
        shown = {
            "outcome": TIER_OUTCOME[tier],
            "note": "出目は非表示（内部ログのみ保持）",
        }
    return {"reveal_dice": reveal_dice, "attempted": True, "shown_to_player": shown}


# ---------------------------------------------------------------------------
# 構造化ログ（動画化を見据える。make_log_entry を実運用に接続）
# ---------------------------------------------------------------------------


def cost_applied(action_result: dict) -> dict:
    """この判定で「払った代償」を機械可読にまとめる。

      mp        : I-2 の機構コスト（status_delta の mp.cur 消費量, 正の値）。
      id5_fired : I-D5（得た＝失った）が発火したか（success_with_cost）。
    """
    r = action_result
    mp = 0
    for d in r.get("status_delta", []) or []:
        change = d.get("change", {}) or {}
        mp += -int(change.get("mp.cur", 0))
    tier = (r.get("resolve") or {}).get("tier")
    return {"mp": mp, "id5_fired": tier == _ID5_TIER}


def make_play_log_entry(
    action_result: dict,
    *,
    turn: int,
    decision_id: str,
    chosen: str,
    consequence: str,
    scene_ref: str,
    reveal_dice: bool = DEFAULT_REVEAL_DICE,
) -> dict:
    """判定を「動画化を見据えた」構造化ログの1エントリにする（decision_log の拡張）。

    誰が(char)/何を(action_type, chosen)/成否(tier)/代償(cost_applied)/結果(consequence)
    を機械可読で持つ。**出目(dice)は reveal_dice に関わらず必ず残す**（内部真実の保持）。
    D1 の器 make_log_entry を通して resolve を verbatim 内包する（seed で再現可能）。
    """
    r = action_result
    attempted = r.get("attempted", True)
    res = r.get("resolve") or {}
    # D1 の器に接続：resolve をそのまま包む（seed 込み＝動画の再生成が可能）。
    envelope = make_log_entry(res, actor=r.get("char"), action=r.get("action_type")) if attempted else None

    return {
        "turn": turn,
        "decision_id": decision_id,
        "chosen": chosen,
        "char": r.get("char"),
        "action_type": r.get("action_type"),
        "attempted": attempted,
        "blocked": r.get("blocked"),
        "dice": res.get("dice"),            # 内部真実：非表示モードでも残す
        "roll_total": res.get("roll_total"),
        "modifier": r.get("modifier"),
        "total": res.get("total"),
        "target": r.get("target"),
        "tier": res.get("tier"),
        "cost_applied": cost_applied(r),
        "consequence": consequence,
        "status_delta": r.get("status_delta", []) or [],
        "scene_ref": scene_ref,
        "reveal_dice": reveal_dice,
        "seed": res.get("seed"),            # 再現用（動画再生成のため）
        "resolve": (envelope or {}).get("resolve"),  # make_log_entry 経由の verbatim
    }


def append_play_log(entry: dict, path: str | Path = "meta/play_log.yaml") -> None:
    """play_log.yaml の末尾に 1 エントリ追記する（読み→append→書き戻し）。

    書込許可は editor（meta 領域）。ここはその器。
    """
    if yaml is None:  # pragma: no cover
        raise RuntimeError("pyyaml が必要です（pip install pyyaml）。")
    p = Path(path)
    header = ""
    log: list = []
    if p.exists():
        text = p.read_text(encoding="utf-8")
        # 先頭のコメントヘッダ（# 行）は保存して復元する。
        header_lines = []
        for ln in text.splitlines():
            if ln.startswith("#") or ln.strip() == "":
                header_lines.append(ln)
            else:
                break
        header = "\n".join(header_lines).rstrip() + "\n\n" if header_lines else ""
        loaded = yaml.safe_load(text)
        if isinstance(loaded, list):
            log = loaded
    log.append(entry)
    p.write_text(header + _dump(log), encoding="utf-8")


# ---------------------------------------------------------------------------
# 回帰
# ---------------------------------------------------------------------------


def regression() -> int:
    all_ok = True

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        print(f"    [{'OK  ' if ok else 'MISS'}] {name}: {detail}")
        if not ok:
            all_ok = False

    print("===== play_log 回帰（D3）=====")

    # D2 の供給層を使って本物の判定結果を作る（status 連動）。
    from status_resolve import load_status, resolve_action

    status = load_status("canon/status.yaml")

    # 0) 既定は表示（reveal_dice=true）。config/play.yaml も true。
    cfg = load_reveal_dice("config/play.yaml")
    check("既定は出目表示（config/play.yaml）", DEFAULT_REVEAL_DICE is True and cfg is True,
          f"DEFAULT={DEFAULT_REVEAL_DICE} config={cfg}")

    # 1) success_with_cost を出す判定（H 魔法, mod 0, target 7, seed 3 → dice[2,5]=7）。
    swc = resolve_action("magic", "H", target=7, status=status, seed=3)
    swc_ok = swc["resolve"]["tier"] == "success_with_cost"
    check("success_with_cost の実例", swc_ok,
          f"dice={swc['resolve']['dice']} total={swc['resolve']['total']} "
          f"target={swc['resolve']['target']} tier={swc['resolve']['tier']}")

    # 2) reveal_dice=true と false で player 提示が変わる。
    shown_true = present_result(swc, reveal_dice=True)["shown_to_player"]
    shown_false = present_result(swc, reveal_dice=False)["shown_to_player"]
    present_ok = (
        "dice" in shown_true and "tier" in shown_true      # true は出目を見せる
        and "dice" not in shown_false and "tier" not in shown_false  # false は伏せる
        and "outcome" in shown_false                       # false は帰結の形だけ
    )
    check("提示は reveal で変わる", present_ok,
          f"true.keys={sorted(shown_true)} / false.keys={sorted(shown_false)}")

    # 3) ログは reveal に関わらず完全（出目を必ず残す）。
    consequence = (
        "刻印は読めた——最後の一画で光が引き、読み返される感触だけが残る。"
        "女に指先の灯を見られ、玩具の石と笑った顔が消える。得た（断片）＝失った（露見せぬ H 像）。"
    )
    e_true = make_play_log_entry(swc, turn=1, decision_id="D1",
                                 chosen="B（灯火で刻印を読む）", consequence=consequence,
                                 scene_ref="playtest-01#s2", reveal_dice=True)
    e_false = make_play_log_entry(swc, turn=1, decision_id="D1",
                                  chosen="B（灯火で刻印を読む）", consequence=consequence,
                                  scene_ref="playtest-01#s2", reveal_dice=False)
    log_complete = (
        e_true["dice"] == [2, 5] and e_false["dice"] == [2, 5]   # 両モードとも出目を保持
        and e_true["total"] == e_false["total"] == 7
        and e_true["seed"] == e_false["seed"] == 3
        and e_true["resolve"]["tier"] == "success_with_cost"     # D1 器に verbatim 接続
    )
    check("ログは両モードとも完全（出目保持）", log_complete,
          f"true.dice={e_true['dice']} false.dice={e_false['dice']} "
          f"seed={e_true['seed']} resolve.tier={e_true['resolve']['tier']}")

    # 4) success_with_cost で cost_applied が記録される（mp=I-2, id5_fired=I-D5）。
    ca = e_true["cost_applied"]
    cost_ok = (
        ca["mp"] == 2 and ca["id5_fired"] is True
        and e_true["consequence"] == consequence and consequence != ""
        and e_true["status_delta"] == [
            {"char": "H", "change": {"mp.cur": -2}, "cause": "魔法発動 (I-2, magic)"}
        ]
    )
    check("success_with_cost の cost_applied 記録", cost_ok,
          f"cost_applied={ca} status_delta={e_true['status_delta']}")

    # 5) 他 tier の cost_applied：full_success は id5_fired=false。
    #    H 魔法 mod0, target7 で total>=10 になる seed を探す（full_success）。
    fs = None
    for s in range(0, 5000):
        r = resolve_action("magic", "H", target=7, status=status, seed=s)
        t = r["resolve"]["tier"]
        if t == "full_success":
            fs = r
            break
    fs_entry = make_play_log_entry(fs, turn=2, decision_id="D2", chosen="—",
                                   consequence="望みが叶う。代償なし。", scene_ref="regress",
                                   reveal_dice=True)
    fs_ok = fs is not None and fs_entry["cost_applied"]["id5_fired"] is False
    check("full_success は id5_fired=false", fs_ok,
          f"seed={fs['resolve']['seed'] if fs else None} "
          f"tier={fs['resolve']['tier'] if fs else None} "
          f"cost_applied={fs_entry['cost_applied']}")

    # 6) MP 不足で弾かれた判定もログに残る（attempted=false, blocked, resolve=None）。
    low = {"characters": {"H": {**status["characters"]["H"]}}}
    low["characters"]["H"] = {**status["characters"]["H"], "mp": {"cur": 1, "max": 10}}
    blocked = resolve_action("magic", "H", target=7, status=low, seed=3)
    b_entry = make_play_log_entry(blocked, turn=3, decision_id="D3",
                                  chosen="C（もう一度灯火）",
                                  consequence="灯を保てない。試みる前に指先が翳る。",
                                  scene_ref="regress", reveal_dice=True)
    blocked_ok = (
        b_entry["attempted"] is False and b_entry["blocked"] == "insufficient_mp"
        and b_entry["dice"] is None and b_entry["resolve"] is None
        and b_entry["cost_applied"]["mp"] == 0
    )
    check("弾かれた判定もログに残る", blocked_ok,
          f"attempted={b_entry['attempted']} blocked={b_entry['blocked']} "
          f"cost_applied={b_entry['cost_applied']}")

    # 7) append_play_log の往復（scratchpad に書いて読み戻す。committed ファイルは触らない）。
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "sdnd_play_log_regress.yaml"
    if tmp.exists():
        tmp.unlink()
    tmp.write_text("# test header\n\n", encoding="utf-8")
    append_play_log(e_true, tmp)
    append_play_log(fs_entry, tmp)
    reloaded = yaml.safe_load(tmp.read_text(encoding="utf-8"))
    roundtrip_ok = (
        isinstance(reloaded, list) and len(reloaded) == 2
        and reloaded[0]["tier"] == "success_with_cost"
        and reloaded[0]["dice"] == [2, 5]
        and tmp.read_text(encoding="utf-8").startswith("# test header")
    )
    check("append_play_log の往復（ヘッダ保存）", roundtrip_ok,
          f"n={len(reloaded) if isinstance(reloaded, list) else 'N/A'} "
          f"[0].tier={reloaded[0]['tier'] if reloaded else None}")
    tmp.unlink(missing_ok=True)

    print()
    print("PLAY-LOG REGRESSION:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _demo(seed: int) -> int:
    from status_resolve import load_status, resolve_action
    status = load_status("canon/status.yaml")
    r = resolve_action("magic", "H", target=7, status=status, seed=seed)
    print("--- reveal_dice = TRUE（既定・表示）---")
    print(_dump(present_result(r, reveal_dice=True)))
    print("--- reveal_dice = FALSE（隠しモード）---")
    print(_dump(present_result(r, reveal_dice=False)))
    print("--- 構造化ログ・エントリ（出目は常に残る）---")
    entry = make_play_log_entry(
        r, turn=1, decision_id="D1", chosen="B（灯火で刻印を読む）",
        consequence="（tier の帰結を writer が散文で埋める）", scene_ref="playtest-01#s2",
    )
    print(_dump([entry]))
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="出目表示モード・tier 帰結・構造化ログ（動画化を見据える）D3."
    )
    ap.add_argument("--regression", action="store_true", help="内蔵回帰を実行")
    ap.add_argument("--demo", action="store_true", help="提示とログの見え方を表示")
    ap.add_argument("--seed", type=int, default=3, help="--demo で使うシード")
    args = ap.parse_args(argv)

    if args.regression:
        return regression()
    if args.demo:
        return _demo(args.seed)
    ap.error("--regression か --demo を指定してください")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
