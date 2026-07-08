"""qa_run.py — ハイブリッド QA 統合ランナー（sdnd-ordia, Q4 / 道A）.

外部 API を叩かない。CODE 判定を先に走らせ、**早期 FAIL** でトークンを節約する:

  Step1  CODE 判定（qa_deterministic の C-9.3 / C-9.6 / C-11.1 / C-11.3）
  Step2  早期 FAIL — CODE 段に Blocker/Major があれば、意味判断の小片パックを
         生成せずに終了し、writer 差し戻し用レポートを出す。
         「壊れているものに意味判断は不要」= ここがトークン節約の要。
  Step3  CODE 通過時のみ、Q2 の抽出関数で **意味判断用の小片パック** を生成し
         qa/reports/pending-llm-<ep>.md に出力する（**LLM は呼ばない**）。
  Step4  qa/reports/consistency-<ep>.md に CODE 判定・早期 FAIL の有無・
         意味判断が pending か・想定/節約 LLM 判断数を明記する。

意味判断（C-11.4 / C-11.2 / C-9.7/C-10 / C-9.5）は、pending-llm パックを
**Claude Code セッション内**で読んで下す（外部 API 不要）。判定は
consistency レポートに統合する。運用は CLAUDE.md の QA セクション参照。

qa_llm.py（API 経路）は温存。ここでは import も起動もしない。将来 API に
切り替える場合は emit_semantic_work() を call_llm() に差し替える（Step3 の境界）。

CLI:
  python qa_run.py <episode.md> [--status canon/status.yaml] [--out-dir qa/reports]
  python qa_run.py --regression
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
from pathlib import Path

import qa_deterministic as qd

# Windows console default cp932 chokes on CJK output; force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# CODE 段でこの重大度が出たら早期 FAIL（Warning は蓄積注意なので止めない）。
EARLY_FAIL_SEVERITIES = ("Blocker", "Major")

# C-11.2 の意味判断で Claude Code に渡す理の定義（invariants I-1 の要約）。
RI_DEFINITION = (
    "『理（ことわり）』は世界の根本律で、何者もそこから外れられない。"
    "理に近づく・触れる・破る行為には必ず対価（代償）が発生し、無償では成立しない（I-1）。"
)

# 意味判断項目ごとの「問い」と、下し得る重大度（Claude Code が記入する）。
QUESTIONS: dict[str, dict] = {
    "C-11.4": {
        "title": "意味的重複（飾り選択）",
        "question": (
            "各 option の intended_shift だけを見て、2つ以上が同じ価値軸を動かすだけで"
            "互いに区別のつく帰結を持たないか。全 option 同一なら Major、一部が飾りなら"
            "Warning、区別できれば 通過。"
        ),
        "severities": "通過 / Warning / Major",
    },
    "C-11.2": {
        "title": "理干渉",
        "question": (
            "この option は『理』に干渉（破る/歪める）し、かつ対価が label/intended_shift"
            "に描かれていないか。対価なしの理干渉なら Blocker、対価ありなら 通過、"
            "そもそも干渉でなければ 通過。"
        ),
        "severities": "通過 / Blocker",
    },
    "C-9.7/C-10": {
        "title": "数値の話者判定（可視性）",
        "question": (
            "この数値は誰の知覚か。現地人の視点/台詞/内語、または客観の地の文、"
            "帰属不明なら Major（I-4 / C-10）。転生者の内語・独白・転生者同士の会話なら 通過。"
        ),
        "severities": "通過 / Major",
    },
    "C-9.5": {
        "title": "変化量の妥当性",
        "question": (
            "変化量は本文の事象規模に見合うか（例:「かすり傷」で HP-15、"
            "「軽い呪文」で MP-8 は不相応）。不相応なら Warning、妥当なら 通過。"
        ),
        "severities": "通過 / Warning",
    },
}


# ---------------------------------------------------------------------------
# Step1: CODE 判定
# ---------------------------------------------------------------------------


def run_code_checks(meta: dict, status: dict) -> list[dict]:
    """qa_deterministic の CODE 4 項目を判定して返す。"""
    return qd.check_all(meta, status)


def blocking_verdicts(verdicts: list[dict]) -> list[dict]:
    """早期 FAIL の対象（Blocker/Major）だけを抜き出す。"""
    return [v for v in verdicts if v["verdict"] in EARLY_FAIL_SEVERITIES]


# ---------------------------------------------------------------------------
# Step3: 意味判断用の小片（LLM は呼ばない・純粋なコード）
# ---------------------------------------------------------------------------


def semantic_candidates(meta: dict, episode_text: str) -> dict[str, list[dict]]:
    """Q2 の抽出で、各 LLM 項目に渡す小片を集める。判定はしない。

    - C-11.4: options の id + intended_shift だけ（本文・label は渡さない）
    - C-11.2: flag_ri_interference でフラグされた option だけ
    - C-9.7/C-10: extract_numeric_mentions の各数値言及（該当文±前後1文）
    - C-9.5: extract_cause_pairs の delta ごと（本文一致した最上位候補1つ）
    """
    decision = meta.get("decision")
    cands: dict[str, list[dict]] = {k: [] for k in QUESTIONS}

    options = (decision or {}).get("options") or []
    if decision and len(options) >= 2:
        cands["C-11.4"].append({
            "snippet": "\n".join(
                f"{o.get('id', '?')}: {o.get('intended_shift', '')}" for o in options
            ),
            "meta": {"option_ids": [o.get("id") for o in options]},
        })

    for c in qd.flag_ri_interference(decision)["candidates"]:
        cands["C-11.2"].append(c)

    for c in qd.extract_numeric_mentions(episode_text)["candidates"]:
        cands["C-9.7/C-10"].append(c)

    seen: set = set()
    for c in qd.extract_cause_pairs(meta.get("status_delta"), episode_text)["candidates"]:
        di = c["meta"].get("delta_index")
        if di in seen or not c.get("snippet"):
            continue
        seen.add(di)
        cands["C-9.5"].append(c)

    return cands


def expected_llm_calls(cands: dict[str, list[dict]]) -> int:
    """このパックを判定するのに要する意味判断（≒LLM 呼び出し）の数。"""
    return sum(len(v) for v in cands.values())


# ---------------------------------------------------------------------------
# レポート描画
# ---------------------------------------------------------------------------


def render_pending_md(ep_id: str, cands: dict[str, list[dict]]) -> str:
    """意味判断待ちの小片パック（Claude Code が読んで重大度を記入する）。"""
    n = expected_llm_calls(cands)
    out: list[str] = []
    out.append(f"# pending-llm-{ep_id} — 意味判断の小片パック")
    out.append("")
    out.append("> qa_run.py が CODE 段通過後に生成。**外部 API は使わない。**")
    out.append("> Claude Code セッションが各小片を読み、重大度を記入する。")
    out.append(f"> 記入後、判定を qa/reports/consistency-{ep_id}.md に統合する（editor 相当）。")
    out.append("")
    out.append(f"想定 LLM 判断数: **{n}**")
    out.append("")
    for item, meta_q in QUESTIONS.items():
        pieces = cands.get(item, [])
        out.append(f"## {item} — {meta_q['title']}（候補 {len(pieces)}）")
        out.append(f"問い: {meta_q['question']}")
        out.append(f"取り得る判定: {meta_q['severities']}")
        if item == "C-11.2" and pieces:
            out.append(f"理の定義: {RI_DEFINITION}")
        if not pieces:
            out.append("")
            out.append("（候補なし）")
            out.append("")
            continue
        for i, c in enumerate(pieces, start=1):
            out.append("")
            out.append(f"### 候補 {i}")
            out.append("snippet:")
            out.append("```")
            out.append(str(c.get("snippet", "")))
            out.append("```")
            out.append(f"meta: {c.get('meta', {})}")
            out.append("判定: ____（記入）    理由: ____（記入）")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_consistency_md(
    ep_id: str,
    code_verdicts: list[dict],
    early_fail: bool,
    blocking: list[dict],
    pending_rel: str | None,
    n_calls: int,
) -> str:
    """CODE 判定・早期FAIL・pending 参照・想定/節約 LLM 判断数を明記。"""
    out: list[str] = []
    out.append(f"# consistency-{ep_id} — 整合性QA レポート")
    out.append("")
    out.append("生成: qa_run.py（Q4 / 道A・外部API不使用）")
    out.append("")
    out.append("## CODE 判定（決定論・qa_deterministic）")
    out.append("")
    out.append("| 項目 | 判定 | 理由 |")
    out.append("|---|---|---|")
    for v in code_verdicts:
        reason = str(v.get("reason", "")).replace("|", "\\|")
        out.append(f"| {v['item']} | {v['verdict']} | {reason} |")
    out.append("")
    if early_fail:
        names = ", ".join(f"{v['item']}={v['verdict']}" for v in blocking)
        out.append("## 早期FAIL: **あり**")
        out.append("")
        out.append(f"- CODE 段に Blocker/Major（{names}）。**意味判断はスキップ**。")
        out.append("- 「壊れているものに意味判断は不要」。writer に差し戻す。")
        out.append(f"- スキップした意味判断数（節約）: **{n_calls}**（LLM 未起動）")
        out.append("")
        out.append("## 総合判定: **FAIL（writer 差し戻し）**")
    else:
        out.append("## 早期FAIL: なし")
        out.append("")
        out.append("- CODE 段 通過。意味判断は **pending**。")
        out.append(f"- 小片パック: `{pending_rel}`")
        out.append(f"- 想定 LLM 判断数: **{n_calls}**（Claude Code セッション内で判定）")
        out.append("")
        out.append("## 総合判定: **PENDING-LLM（CODE OK、意味判断待ち）**")
    out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Step3 の境界（差し替え点）: いまは小片パックをファイル出力する。
# 将来 API 方針に切り替えるなら、この関数を qa_llm 呼び出しに差し替える。
# ---------------------------------------------------------------------------


def emit_semantic_work(ep_id: str, cands: dict[str, list[dict]], out_dir: Path) -> Path:
    """SWAP POINT: 意味判断用の小片パックを pending-llm-<ep>.md に書き出す。

    将来 API を使うなら、ここを `call_llm(cands)`（qa_llm 経由）に差し替えて、
    ファイル出力の代わりに判定結果を返すようにする。呼び出し側（run）は
    「CODE 通過時にだけ意味判断ワークを起こす」構造のまま変えなくてよい。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pending-llm-{ep_id}.md"
    path.write_text(render_pending_md(ep_id, cands), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 統合ランナー
# ---------------------------------------------------------------------------


def run(episode_path: str, status_path: str = "canon/status.yaml",
        out_dir: str = "qa/reports") -> dict:
    """CODE 判定 → 早期FAIL → 通過時のみ小片パック出力。API は叩かない。"""
    text = qd.read_file(episode_path)
    meta = qd.parse_episode_meta(text)
    status = qd.parse_status(qd.read_file(status_path))
    ep_id = meta.get("ep_id") or Path(episode_path).stem
    out = Path(out_dir)

    # Step1
    code_verdicts = run_code_checks(meta, status)
    blocking = blocking_verdicts(code_verdicts)
    out.mkdir(parents=True, exist_ok=True)

    if blocking:
        # Step2: 早期 FAIL。小片パックは生成/出力せず、意味判断もしない。
        # 節約数だけは抽出候補数から算出（決定論・トークン非消費）。
        skipped = expected_llm_calls(semantic_candidates(meta, text))
        cons = render_consistency_md(ep_id, code_verdicts, True, blocking, None, skipped)
        cons_path = out / f"consistency-{ep_id}.md"
        cons_path.write_text(cons, encoding="utf-8")
        return {
            "ep_id": ep_id, "status": "EARLY-FAIL", "code_verdicts": code_verdicts,
            "blocking": blocking, "pending_path": None,
            "llm_calls_skipped": skipped, "consistency_path": str(cons_path),
        }

    # Step3: CODE 通過。小片パックを出力（LLM は呼ばない）。
    cands = semantic_candidates(meta, text)
    n_calls = expected_llm_calls(cands)
    pending_path = emit_semantic_work(ep_id, cands, out)
    cons = render_consistency_md(
        ep_id, code_verdicts, False, [], pending_path.name, n_calls
    )
    cons_path = out / f"consistency-{ep_id}.md"
    cons_path.write_text(cons, encoding="utf-8")
    return {
        "ep_id": ep_id, "status": "PENDING-LLM", "code_verdicts": code_verdicts,
        "blocking": [], "pending_path": str(pending_path),
        "llm_calls_expected": n_calls, "consistency_path": str(cons_path),
    }


def print_summary(result: dict) -> None:
    print(f"===== qa_run: {result['ep_id']} =====")
    for v in result["code_verdicts"]:
        print(f"  {v['item']:8s}  {v['verdict']:8s}  — {v['reason']}")
    print(f"  総合: {result['status']}")
    if result["status"] == "EARLY-FAIL":
        names = ", ".join(f"{v['item']}={v['verdict']}" for v in result["blocking"])
        print(f"  早期FAIL: {names}")
        print(f"  意味判断スキップ（節約）: {result['llm_calls_skipped']} 件（LLM 未起動）")
    else:
        print(f"  小片パック: {result['pending_path']}")
        print(f"  想定 LLM 判断数: {result['llm_calls_expected']} 件（要 Claude Code 判定）")
    print(f"  レポート: {result['consistency_path']}")


# ---------------------------------------------------------------------------
# 回帰（すべてオフライン・API なし・出力は temp ディレクトリへ）
# ---------------------------------------------------------------------------


def _synthetic_status() -> dict:
    """回帰の合成ケース用。実 canon と同型（H のみ）。"""
    return qd.parse_status(qd.read_file("canon/status.yaml"))


def regression() -> int:
    all_ok = True

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        print(f"    [{'OK  ' if ok else 'MISS'}] {name}: {detail}")
        if not ok:
            all_ok = False

    tmp = Path(tempfile.mkdtemp(prefix="qa_run_reg_"))
    print(f"===== qa_run 回帰（出力: {tmp}）=====")

    # 1) MP不足 (C-11.1 Major) → 早期FAIL、pending 未生成
    r = run("story/ep-00-b1test-violation.md", out_dir=str(tmp))
    pending_exists = (tmp / f"pending-llm-{r['ep_id']}.md").exists()
    check("b1test-violation 早期FAIL(C-11.1)",
          r["status"] == "EARLY-FAIL"
          and any(v["item"] == "C-11.1" and v["verdict"] == "Major" for v in r["blocking"])
          and not pending_exists,
          f"status={r['status']} pending_written={pending_exists} "
          f"skipped={r.get('llm_calls_skipped')}")

    # 2) 範囲外 (C-9.3 Major) → 早期FAIL（a2test: mp 2-8=-6）
    r = run("story/ep-00-a2test.md", out_dir=str(tmp))
    pending_exists = (tmp / f"pending-llm-{r['ep_id']}.md").exists()
    check("a2test 早期FAIL(C-9.3 範囲外)",
          r["status"] == "EARLY-FAIL"
          and any(v["item"] == "C-9.3" and v["verdict"] == "Major" for v in r["blocking"])
          and not pending_exists,
          f"status={r['status']} pending_written={pending_exists} "
          f"skipped={r.get('llm_calls_skipped')}")

    # 3) B1 正しい版 → CODE 全通過、小片パック生成
    r = run("story/ep-00-b1test.md", out_dir=str(tmp))
    pending_exists = (tmp / f"pending-llm-{r['ep_id']}.md").exists()
    check("b1test CODE通過→pack生成",
          r["status"] == "PENDING-LLM" and pending_exists
          and r["llm_calls_expected"] > 0,
          f"status={r['status']} pending_written={pending_exists} "
          f"expected={r.get('llm_calls_expected')}")

    # 4) A3 → 通過し、数値言及が小片として載る（C-9.7/C-10）
    r = run("story/ep-00-a3test.md", out_dir=str(tmp))
    cands = semantic_candidates(
        qd.parse_episode_meta(qd.read_file("story/ep-00-a3test.md")),
        qd.read_file("story/ep-00-a3test.md"),
    )
    check("a3test 数値言及が小片に載る",
          r["status"] == "PENDING-LLM" and len(cands["C-9.7/C-10"]) == 2,
          f"status={r['status']} 数値小片={len(cands['C-9.7/C-10'])}")

    # 5) 存在しない char (C-9.6 Major) → 早期FAIL（合成メタ）
    bad_char_meta = {"ep_id": "syn-c96", "status_delta": [
        {"char": "現地人女", "change": {"hp.cur": -1}, "cause": "架空"}]}
    v = run_code_checks(bad_char_meta, _synthetic_status())
    blk = blocking_verdicts(v)
    check("合成 C-9.6(存在しないchar) 早期FAIL",
          any(b["item"] == "C-9.6" and b["verdict"] == "Major" for b in blk),
          f"blocking={[b['item'] for b in blk]}")

    # 6) 5択 (C-11.3 Warning) → 早期FAIL しない（Warning は止めない）
    five = {"ep_id": "syn-5opt", "status_delta": [], "decision": {
        "id": "D1", "options": [
            {"id": c, "requires": {}, "intended_shift": f"軸{c}"}
            for c in "ABCDE"]}}
    v = run_code_checks(five, _synthetic_status())
    blk = blocking_verdicts(v)
    c113 = next(x for x in v if x["item"] == "C-11.3")
    check("合成 C-11.3(5択)=Warning は早期FAILしない",
          c113["verdict"] == "Warning" and not blk,
          f"C-11.3={c113['verdict']} blocking={[b['item'] for b in blk]}")

    # 7) 小片パック builder: 違反版 D が C-11.2 候補に載る（gate とは独立）
    v_meta = qd.parse_episode_meta(qd.read_file("story/ep-00-b1test-violation.md"))
    v_text = qd.read_file("story/ep-00-b1test-violation.md")
    vc = semantic_candidates(v_meta, v_text)
    ri_ids = [c["meta"].get("option_id") for c in vc["C-11.2"]]
    check("builder: 違反版Dが C-11.2 候補に載る",
          ri_ids == ["D"],
          f"C-11.2 候補 option_ids={ri_ids}（本 runで実際は早期FAILしパック未出力）")

    print()
    print("QA_RUN REGRESSION:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Hybrid QA runner (Q4 / path A, no external API)."
    )
    ap.add_argument("episode", nargs="?", help="path to episode .md")
    ap.add_argument("--status", default="canon/status.yaml")
    ap.add_argument("--out-dir", default="qa/reports")
    ap.add_argument("--regression", action="store_true")
    args = ap.parse_args(argv)

    if args.regression:
        return regression()
    if not args.episode:
        ap.error("episode is required (or use --regression)")

    result = run(args.episode, args.status, args.out_dir)
    print_summary(result)
    # FAIL は非ゼロ、PENDING は 0。
    return 1 if result["status"] == "EARLY-FAIL" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
