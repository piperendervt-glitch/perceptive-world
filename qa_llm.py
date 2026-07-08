"""qa_llm.py — HYBRID QA の LLM 判断側（sdnd-ordia, Q3）.

Q2（qa_deterministic.py）がコードで切り出した「小片」を入力に、意味判断だけを
軽量 Claude に問う。各関数は:
  - 入力は小片のみ（本文全体・チェックリスト全文は渡さない）。
  - temperature=0（llm.yaml）、JSON 強制（output_config.format）、
    壊れたら 1 回だけ再要求。
  - LLM は「意味の判定」だけを返す。PASS/Major/Blocker 等への写像はコード側。

対象項目:
  C-11.4  意味的重複（飾り選択）   : 入力 = options の id と intended_shift だけ
  C-11.2  理干渉                  : 入力 = フラグ済み option の label/shift + 理の定義
  C-9.7/C-10 話者判定            : 入力 = 数値言及の該当文±前後1文
  C-12.1/C-12.2 選択反映・整合   : 入力 = chosen + consequence + 次話本文（抜粋）
  C-9.5   変化量妥当性            : 入力 = delta + 該当事象の描写1〜2文

LLM 接続は llm_provider.LLMProvider 経由。オフライン回帰は RecordedProvider を使う。

CLI:
  python qa_llm.py --selftest            # オフライン回帰（RecordedProvider）
  python qa_llm.py <episode.md> --live   # 実 LLM（要 ANTHROPIC_API_KEY）
"""

from __future__ import annotations

import argparse
import io
import json
import sys

import qa_deterministic as qd
from llm_provider import (
    LLMError,
    RecordedProvider,
    load_llm_config,
    make_provider,
)

# Windows console default cp932 chokes on CJK output; force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class LLMOutputError(LLMError):
    """LLM returned non-JSON twice (after one re-request)."""


# ---------------------------------------------------------------------------
# JSON asking (temperature=0 lives in the provider; JSON discipline lives here)
# ---------------------------------------------------------------------------


def _strip_fences(text: str) -> str:
    """Tolerate ```json ... ``` fences some models add despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _ask_json(provider, system: str, user: str, schema: dict) -> dict:
    """Ask once, parse; on broken JSON re-request exactly once, then give up."""
    raw = provider.complete(system, user, schema)
    try:
        return json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, ValueError):
        nudge = (
            user
            + "\n\n必ず有効な JSON だけを返してください。"
            "前後に説明文・コードフェンス・余計な文字を付けないこと。"
        )
        raw2 = provider.complete(system, nudge, schema)
        try:
            return json.loads(_strip_fences(raw2))
        except (json.JSONDecodeError, ValueError) as e:
            raise LLMOutputError(
                f"LLM returned non-JSON twice. last output:\n{raw2[:300]}"
            ) from e


# ---------------------------------------------------------------------------
# 理（ことわり）の定義 — C-11.2 の LLM に渡す 2 文（invariants I-1 の要約）
# ---------------------------------------------------------------------------

RI_DEFINITION = (
    "『理（ことわり）』は世界の根本律で、何者もそこから外れられない。"
    "理に近づく・触れる・破る行為には必ず対価（代償）が発生し、無償では成立しない（I-1）。"
)


# ---------------------------------------------------------------------------
# C-11.4  意味的重複（飾り選択）
# ---------------------------------------------------------------------------

_DUP_SYS = (
    "あなたは物語の選択肢設計をレビューします。各選択肢が動かす価値"
    "（intended_shift）だけを見て、実質的に区別のつかない選択肢がないか判定します。"
    "本文は渡されません。JSON だけを返してください。"
)
_DUP_SCHEMA = {
    "type": "object",
    "properties": {
        "duplicate": {"type": "boolean"},
        "pair": {"type": "array", "items": {"type": "string"}},
        "all_same": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["duplicate", "pair", "all_same", "reason"],
    "additionalProperties": False,
}


def judge_semantic_duplicate(decision: dict | None, provider) -> dict:
    """C-11.4: options の id + intended_shift だけを LLM に渡して飾り重複を判定。"""
    options = (decision or {}).get("options") or []
    if len(options) < 2:
        return {"item": "C-11.4", "verdict": "通過", "reason": "options<2",
                "needs_llm": False, "input_chars": 0}
    lines = "\n".join(
        f"- {o.get('id', '?')}: {o.get('intended_shift', '')}" for o in options
    )
    user = (
        "# 各選択肢の intended_shift（内部記録・本文ではない）\n"
        f"{lines}\n\n"
        "# 問い\n"
        "2つ以上の選択肢が同じ価値軸を動かすだけで、互いに区別のつく帰結を持たない"
        "とき、それらは「飾り（重複）」です。すべてが実質同一なら all_same=true。\n"
        '返す JSON: {"duplicate": <bool>, "pair": ["<id>","<id>"], '
        '"all_same": <bool>, "reason": "<20字以内>"}'
    )
    j = _ask_json(provider, _DUP_SYS, user, _DUP_SCHEMA)
    if j.get("all_same"):
        verdict = "Major"          # 全 option 同一 → 決定として不成立
    elif j.get("duplicate"):
        verdict = "Warning"        # 一部が飾り
    else:
        verdict = "通過"
    return {
        "item": "C-11.4", "verdict": verdict, "llm": j,
        "reason": j.get("reason", ""), "pair": j.get("pair", []),
        "needs_llm": True, "input_chars": len(user),
    }


# ---------------------------------------------------------------------------
# C-11.2  理干渉（Q2 flag_ri_interference でフラグされた option だけを問う）
# ---------------------------------------------------------------------------

_RI_SYS = (
    "あなたは異世界小説の整合性チェッカーです。世界の根本律『理』に関する選択肢を"
    "判定します。JSON だけを返してください。"
)
_RI_SCHEMA = {
    "type": "object",
    "properties": {
        "ri_interference": {"type": "boolean"},
        "price_present": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["ri_interference", "price_present", "reason"],
    "additionalProperties": False,
}


def judge_ri_interference(candidate: dict, provider) -> dict:
    """C-11.2: フラグ済み option の label/intended_shift + 理の定義だけを渡す。"""
    meta = candidate.get("meta", {})
    label = candidate.get("snippet", "")
    shift = meta.get("intended_shift", "")
    user = (
        f"# 理の定義\n{RI_DEFINITION}\n\n"
        "# 判定対象の選択肢（requires=対価 は空）\n"
        f"label: {label}\n"
        f"intended_shift: {shift}\n\n"
        "# 問い\n"
        "この選択肢は『理』に干渉（理を破る/歪める）しますか。またその代償（対価）が"
        "label/intended_shift に描かれていますか。\n"
        '返す JSON: {"ri_interference": <bool>, "price_present": <bool>, '
        '"reason": "<20字以内>"}'
    )
    j = _ask_json(provider, _RI_SYS, user, _RI_SCHEMA)
    if j.get("ri_interference") and not j.get("price_present"):
        verdict = "Blocker"        # 対価なしに理を破る → I-1 違反
    elif j.get("ri_interference"):
        verdict = "通過"           # 理に干渉するが対価あり → 許容
    else:
        verdict = "通過"           # そもそも理干渉ではない（Q2 の誤検出）
    return {
        "item": "C-11.2", "verdict": verdict, "option_id": meta.get("option_id"),
        "llm": j, "reason": j.get("reason", ""),
        "needs_llm": True, "input_chars": len(user),
    }


# ---------------------------------------------------------------------------
# C-9.7 / C-10  話者判定（数値言及の帰属）
# ---------------------------------------------------------------------------

_SPK_SYS = (
    "あなたは可視性規律の検査官です。数値（HP/MP/レベル等）が誰の知覚として現れて"
    "いるかを判定します。ステータス数値は転生者にしか見えません。JSON だけを返す。"
)
_SPK_SCHEMA = {
    "type": "object",
    "properties": {
        "viewpoint": {"type": "string",
                      "enum": ["転生者", "現地人", "地の文", "不明"]},
        "reason": {"type": "string"},
    },
    "required": ["viewpoint", "reason"],
    "additionalProperties": False,
}


def judge_numeric_speaker(candidate: dict, provider) -> dict:
    """C-9.7/C-10: 数値言及の該当文±前後1文だけを渡し、視点を判定。"""
    snippet = candidate.get("snippet", "")
    matched = candidate.get("meta", {}).get("matched", [])
    user = (
        "# 抜粋（該当文±前後1文）\n"
        f"{snippet}\n\n"
        f"# 抽出された数値: {matched}\n\n"
        "# 問い\n"
        "この数値は誰の視点/声で現れていますか。\n"
        "- 転生者の内語・独白・転生者同士の会話 → 転生者\n"
        "- 現地人（非転生者）の視点・台詞・内語 → 現地人\n"
        "- 誰の視点でもない客観の地の文 → 地の文\n"
        "- 判別不能 → 不明\n"
        '返す JSON: {"viewpoint": "<転生者/現地人/地の文/不明>", "reason": "<20字以内>"}'
    )
    j = _ask_json(provider, _SPK_SYS, user, _SPK_SCHEMA)
    vp = j.get("viewpoint")
    if vp == "現地人":
        verdict = "Major"          # I-4 違反（現地人前で数値露出）
    elif vp == "地の文":
        verdict = "Major"          # C-10.1（客観地の文の数値露出）
    elif vp == "不明":
        verdict = "Major"          # C-10.3（帰属不明）
    else:
        verdict = "通過"           # 転生者の知覚 → OK
    return {
        "item": "C-9.7/C-10", "verdict": verdict, "viewpoint": vp,
        "llm": j, "reason": j.get("reason", ""),
        "needs_llm": True, "input_chars": len(user),
    }


# ---------------------------------------------------------------------------
# C-12.1 / C-12.2  選択反映・整合（B2 以降で本使用。関数は Q3 で用意）
# ---------------------------------------------------------------------------

_REFL_SYS = (
    "あなたは分岐整合の検査官です。前話で選ばれた選択が、次話本文に反映され、"
    "矛盾していないかを判定します。JSON だけを返す。"
)
_REFL_SCHEMA = {
    "type": "object",
    "properties": {
        "reflects": {"type": "boolean"},
        "contradicts": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["reflects", "contradicts", "reason"],
    "additionalProperties": False,
}


def judge_choice_reflection(chosen: str, consequence: str,
                            next_excerpt: str, provider) -> dict:
    """C-12.1/C-12.2: chosen + consequence + 次話本文(抜粋) を渡して整合を判定。"""
    user = (
        "# 選ばれた選択\n"
        f"chosen: {chosen}\n"
        f"想定された帰結(consequence): {consequence}\n\n"
        "# 次話の本文（抜粋）\n"
        f"{next_excerpt}\n\n"
        "# 問い\n"
        '返す JSON: {"reflects": <bool 選択が本文に反映されているか>, '
        '"contradicts": <bool 選択と矛盾する描写があるか>, "reason": "<20字以内>"}'
    )
    j = _ask_json(provider, _REFL_SYS, user, _REFL_SCHEMA)
    if j.get("contradicts"):
        verdict = "Major"          # C-12.2 選択と矛盾
    elif not j.get("reflects"):
        verdict = "Major"          # C-12.1 選択が反映されていない
    else:
        verdict = "通過"
    return {
        "item": "C-12.1/C-12.2", "verdict": verdict, "llm": j,
        "reason": j.get("reason", ""),
        "needs_llm": True, "input_chars": len(user),
    }


# ---------------------------------------------------------------------------
# C-9.5  変化量の妥当性
# ---------------------------------------------------------------------------

_MAG_SYS = (
    "あなたは数値変化の妥当性を検査します。変化量が本文の事象規模に見合うかを"
    "判定します。JSON だけを返す。"
)
_MAG_SCHEMA = {
    "type": "object",
    "properties": {
        "plausible": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["plausible", "reason"],
    "additionalProperties": False,
}


def judge_magnitude_plausibility(change: dict, cause: str,
                                 event_snippet: str, provider) -> dict:
    """C-9.5: delta（change+cause）と該当事象の描写1〜2文だけを渡す。"""
    user = (
        "# 数値変化\n"
        f"{change}  (cause: {cause})\n\n"
        "# 該当事象の描写（1〜2文）\n"
        f"{event_snippet}\n\n"
        "# 問い\n"
        "変化量は事象の規模に見合いますか。"
        "（例:「かすり傷」で HP-15、「軽い呪文」で MP-8 は不相応）\n"
        '返す JSON: {"plausible": <bool>, "reason": "<20字以内>"}'
    )
    j = _ask_json(provider, _MAG_SYS, user, _MAG_SCHEMA)
    verdict = "通過" if j.get("plausible") else "Warning"
    return {
        "item": "C-9.5", "verdict": verdict, "llm": j,
        "reason": j.get("reason", ""),
        "needs_llm": True, "input_chars": len(user),
    }


# ---------------------------------------------------------------------------
# Orchestrator: Q2 の抽出小片 -> Q3 の LLM 判定
# ---------------------------------------------------------------------------


def judge_from_extraction(meta: dict, episode_text: str, provider) -> list[dict]:
    """Run every LLM judge over Q2's extracted candidates. Small pieces only."""
    results: list[dict] = []
    decision = meta.get("decision")

    # C-11.4: 全 decision の options（intended_shift のみ）
    if decision:
        results.append(judge_semantic_duplicate(decision, provider))

    # C-11.2: Q2 がフラグした option だけ
    for cand in qd.flag_ri_interference(decision)["candidates"]:
        results.append(judge_ri_interference(cand, provider))

    # C-9.7/C-10: Q2 が抽出した数値言及の小片ごと
    for cand in qd.extract_numeric_mentions(episode_text)["candidates"]:
        results.append(judge_numeric_speaker(cand, provider))

    # C-9.5: Q2 の cause↔事象ペア（本文一致した最上位候補のみ）
    seen_delta: set[int] = set()
    for cand in qd.extract_cause_pairs(meta.get("status_delta"), episode_text)["candidates"]:
        m = cand.get("meta", {})
        di = m.get("delta_index")
        if di in seen_delta or not cand.get("snippet"):
            continue
        seen_delta.add(di)
        results.append(
            judge_magnitude_plausibility(m.get("change", {}), m.get("cause", ""),
                                         cand["snippet"], provider)
        )
    return results


# ---------------------------------------------------------------------------
# Offline regression (RecordedProvider) — proves plumbing + detection direction
# ---------------------------------------------------------------------------


def _recorded_qa_provider() -> RecordedProvider:
    """Responses a lightweight Claude returns for the B1/A2/A3 snippets.

    Keyed by a distinctive substring of each judge's small-snippet prompt. The
    live AnthropicProvider produces these for real; here they are recorded so
    the regression is deterministic and offline.
    """
    return RecordedProvider([
        # C-11.2 — violation option D: 対価なしに理を破る -> Blocker
        ("『理』に働きかけて音そのものを消し去る",
         '{"ri_interference": true, "price_present": false, '
         '"reason": "対価なしで理に干渉"}'),
        # C-11.4 — violation: A と C の intended_shift が実質同一 -> Warning
        ("露見を回避するために動かない",
         '{"duplicate": true, "pair": ["A", "C"], "all_same": false, '
         '"reason": "AとCが実質同一"}'),
        # C-11.4 — correct b1test: 各選択の帰結は別 -> 通過
        ("現地人の知識で情報を得るが",
         '{"duplicate": false, "pair": [], "all_same": false, '
         '"reason": "各選択の帰結は別"}'),
        # C-9.7/C-10 — a3test H の内語 -> 転生者（通過）
        ("もう一度は無理だ",
         '{"viewpoint": "転生者", "reason": "括弧内はHの内語"}'),
        ("動ける、と、歩ける、は違う",
         '{"viewpoint": "転生者", "reason": "括弧内はHの内語"}'),
        # C-9.7/C-10 — 現地人が数値を口にする NG 例 -> 現地人（Major）
        ("あんた、HP がもう半分もないね",
         '{"viewpoint": "現地人", "reason": "現地人が数値を口にする"}'),
        # C-9.5 — a2test 灯火の魔法で MP-8 -> 妥当（通過）
        ("洞窟で灯火の魔法を使った",
         '{"plausible": true, "reason": "詠唱描写に見合う"}'),
    ])


def _line(name: str, ok: bool, detail: str) -> bool:
    print(f"    [{'OK  ' if ok else 'MISS'}] {name}: {detail}")
    return ok


def selftest() -> int:
    """Offline regression: exercise every judge on the B1/A2/A3 small pieces."""
    provider = _recorded_qa_provider()
    all_ok = True
    print("===== LLM judges (Q3, offline RecordedProvider) =====")

    # --- C-11.2 & C-11.4 on B1 violation ---
    v_meta = qd.parse_episode_meta(qd.read_file("story/ep-00-b1test-violation.md"))
    v_dec = v_meta.get("decision")

    dup_v = judge_semantic_duplicate(v_dec, provider)
    all_ok &= _line(
        "C-11.4 b1test-violation", dup_v["verdict"] == "Warning",
        f"verdict={dup_v['verdict']} pair={dup_v.get('pair')} "
        f"(input {dup_v['input_chars']} chars, no body)",
    )

    ri_cands = qd.flag_ri_interference(v_dec)["candidates"]
    ri_v = judge_ri_interference(ri_cands[0], provider)
    all_ok &= _line(
        "C-11.2 b1test-violation", ri_v["verdict"] == "Blocker",
        f"option {ri_v['option_id']} -> {ri_v['verdict']} "
        f"(input {ri_v['input_chars']} chars: label+shift+理定義)",
    )

    # --- C-11.4 on B1 correct (no false positive) ---
    c_meta = qd.parse_episode_meta(qd.read_file("story/ep-00-b1test.md"))
    dup_c = judge_semantic_duplicate(c_meta.get("decision"), provider)
    all_ok &= _line(
        "C-11.4 b1test (correct)", dup_c["verdict"] == "通過",
        f"verdict={dup_c['verdict']} (input {dup_c['input_chars']} chars)",
    )

    # --- C-9.7/C-10 on A3 (H's monologue -> 通過) ---
    a3_text = qd.read_file("story/ep-00-a3test.md")
    a3_cands = qd.extract_numeric_mentions(a3_text)["candidates"]
    a3_verdicts = [judge_numeric_speaker(c, provider) for c in a3_cands]
    a3_ok = a3_cands and all(v["verdict"] == "通過" for v in a3_verdicts)
    all_ok &= _line(
        "C-9.7/C-10 a3test (H monologue)", bool(a3_ok),
        f"n={len(a3_verdicts)} viewpoints={[v['viewpoint'] for v in a3_verdicts]} "
        f"(each input ~{a3_verdicts[0]['input_chars'] if a3_verdicts else 0} chars)",
    )

    # --- C-9.7/C-10 on 現地人 exposure NG snippet -> Major ---
    ng_cand = {
        "snippet": "女は H の顔を覗き込んだ。「あんた、HP がもう半分もないね」 "
                   "H は答えられなかった。",
        "meta": {"matched": ["HP"], "attribution_hint": "speech"},
    }
    ng_v = judge_numeric_speaker(ng_cand, provider)
    all_ok &= _line(
        "C-9.7/C-10 現地人露出 NG", ng_v["verdict"] == "Major",
        f"viewpoint={ng_v['viewpoint']} -> {ng_v['verdict']} "
        f"(input {ng_v['input_chars']} chars)",
    )

    # --- C-9.5 on A2 delta (magnitude) ---
    a2_text = qd.read_file("story/ep-00-a2test.md")
    a2_meta = qd.parse_episode_meta(a2_text)
    a2_pairs = qd.extract_cause_pairs(a2_meta.get("status_delta"), a2_text)["candidates"]
    first = next(c for c in a2_pairs if c["meta"]["delta_index"] == 0)
    mag_v = judge_magnitude_plausibility(
        first["meta"]["change"], first["meta"]["cause"], first["snippet"], provider
    )
    all_ok &= _line(
        "C-9.5 a2test delta0", mag_v["verdict"] == "通過",
        f"plausible={mag_v['llm'].get('plausible')} -> {mag_v['verdict']} "
        f"(input {mag_v['input_chars']} chars)",
    )

    print()
    print(f"LLM calls made (offline): {len(provider.calls)}")
    print("LLM SELFTEST:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="HYBRID QA — LLM judgment side (Q3).")
    ap.add_argument("episode", nargs="?", help="episode .md (with --live)")
    ap.add_argument("--selftest", action="store_true",
                    help="offline regression (RecordedProvider, no network)")
    ap.add_argument("--live", action="store_true",
                    help="call the real qa-role model (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--config", default="config/llm.yaml")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.episode:
        ap.error("episode is required (or use --selftest)")
    if not args.live:
        ap.error("running against an episode requires --live (real LLM); "
                 "for the offline demo use --selftest")

    cfg = load_llm_config(args.config)
    provider = make_provider("qa", cfg)
    meta = qd.parse_episode_meta(qd.read_file(args.episode))
    results = judge_from_extraction(meta, qd.read_file(args.episode), provider)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
