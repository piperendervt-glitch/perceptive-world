"""qa_deterministic.py — CODE-only (deterministic) QA for sdnd-ordia.

Implements the checks that don't require language understanding:
  C-9.3   status_delta の適用後値が [0, max] に収まるか
  C-9.6   status_delta.char が canon/status.yaml に存在するか
  C-11.1  decision.options[*].requires が canon の現在値で満たせるか
  C-11.3  decision.options の個数が [2, 4] に収まるか

No LLM, no temperature, no randomness. Same input -> same output.

CLI:
  python qa_deterministic.py <episode.md>
  python qa_deterministic.py <episode.md> --json
  python qa_deterministic.py --regression
  python qa_deterministic.py <episode.md> --status <path/to/status.yaml>
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "qa_deterministic.py requires PyYAML. Install: pip install pyyaml\n"
    )
    sys.exit(2)

# Windows console default cp932 chokes on CJK output; force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_episode_meta(text: str) -> dict:
    """Extract and parse the trailing YAML meta block from an episode.

    The meta block is delimited by two lines each containing exactly '---'
    at the end of the file. Earlier '---' lines (e.g. horizontal rules
    inside prose) are ignored; the last pair is taken as the meta block.

    Raises ValueError on missing fences or invalid YAML.
    """
    lines = text.rstrip().splitlines()
    fence_idx = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if len(fence_idx) < 2:
        raise ValueError(
            "episode: no trailing meta block (need two '---' fences)"
        )
    start, end = fence_idx[-2], fence_idx[-1]
    body = "\n".join(lines[start + 1 : end])
    try:
        meta = yaml.safe_load(body)
    except yaml.YAMLError as e:
        raise ValueError(f"episode meta YAML invalid: {e}") from e
    if not isinstance(meta, dict):
        raise ValueError(
            f"episode meta did not parse to a mapping "
            f"(got {type(meta).__name__})"
        )
    return meta


def parse_status(text: str) -> dict:
    """Parse canon/status.yaml. Requires top-level 'characters' mapping."""
    try:
        d = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"status.yaml invalid: {e}") from e
    if not isinstance(d, dict) or "characters" not in d:
        raise ValueError("status.yaml missing top-level 'characters' mapping")
    if not isinstance(d["characters"], dict):
        raise ValueError("status.yaml: 'characters' must be a mapping")
    return d


def parse_episode_body(text: str) -> str:
    """Return the reader-visible prose of an episode (no meta, no author-notes).

    Episode layout (see .claude/agents/writer.md):
        # title
        > 著者注（blockquote）
        ---                <- header separator
        <prose>
        ---                <- meta open
        <YAML meta>
        ---                <- meta close

    We take the region between the first '---' and the meta-open '---', then
    drop markdown headings ('#') and blockquote author-notes ('>') so only the
    prose the reader would see remains. This keeps meta commentary (which can
    contain literal 'mp: 5' etc.) out of the extracted candidates.
    """
    lines = text.rstrip().splitlines()
    fence_idx = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if len(fence_idx) >= 3:
        body_lines = lines[fence_idx[0] + 1 : fence_idx[-2]]
    elif len(fence_idx) == 2:
        body_lines = lines[: fence_idx[-2]]
    else:
        body_lines = lines
    kept = [
        ln
        for ln in body_lines
        if not ln.lstrip().startswith("#") and not ln.lstrip().startswith(">")
    ]
    return "\n".join(kept).strip()


# ---------------------------------------------------------------------------
# Sentence segmentation (depth-aware: never split inside （…） or 「…」)
# ---------------------------------------------------------------------------

_OPEN_BRACKETS = "（(「『“"
_CLOSE_BRACKETS = "）)」』”"
_TERMINATORS = "。！？!?"


def split_sentences(text: str) -> list[str]:
    """Split prose into ordered sentences.

    Terminators are 。！？!? and newlines, but ONLY at bracket depth 0 — a
    parenthetical monologue like「（残り MP 2。もう一度は無理だ）」stays a single
    sentence so its attribution (H の内語) is preserved for the LLM.
    """
    sentences: list[str] = []
    buf: list[str] = []
    depth = 0

    def flush() -> None:
        s = "".join(buf).strip()
        if s:
            sentences.append(s)
        buf.clear()

    for ch in text:
        if ch in _OPEN_BRACKETS:
            depth += 1
        elif ch in _CLOSE_BRACKETS and depth > 0:
            depth -= 1
        if ch == "\n":
            if depth == 0:
                flush()
            else:
                buf.append(" ")
            continue
        buf.append(ch)
        if ch in _TERMINATORS and depth == 0:
            flush()
    flush()
    return sentences


# ---------------------------------------------------------------------------
# Path helpers (shorthand: hp -> hp.cur, mp -> mp.cur)
# ---------------------------------------------------------------------------

SHORTHAND = {"hp": "hp.cur", "mp": "mp.cur"}


def resolve_path(key: str) -> str:
    return SHORTHAND.get(key, key)


def get_path(d: dict, dotted: str) -> Any:
    node: Any = d
    for p in dotted.split("."):
        if not isinstance(node, dict) or p not in node:
            raise KeyError(dotted)
        node = node[p]
    return node


def set_path(d: dict, dotted: str, val: Any) -> None:
    parts = dotted.split(".")
    node = d
    for p in parts[:-1]:
        node = node.setdefault(p, {})
    node[parts[-1]] = val


# ---------------------------------------------------------------------------
# CODE checks
# ---------------------------------------------------------------------------


def check_C9_3(deltas: list | None, status: dict) -> dict:
    """C-9.3: hp.cur / mp.cur remain in [0, max] after applying every delta."""
    if not deltas:
        return {
            "item": "C-9.3",
            "verdict": "通過",
            "reason": "status_delta is empty; nothing to apply.",
        }
    sim = copy.deepcopy(status)
    problems: list[str] = []
    for i, d in enumerate(deltas, start=1):
        char = d.get("char")
        change = d.get("change") or {}
        c = sim.get("characters", {}).get(char)
        if c is None:
            # Unknown char: handled by C-9.6; skip range-check.
            continue
        for key, val in change.items():
            path = resolve_path(str(key))
            try:
                cur = get_path(c, path)
            except KeyError:
                # Attribute path doesn't exist in status; not a range-check target.
                continue
            new = (cur or 0) + val
            set_path(c, path, new)
            if path in ("hp.cur", "mp.cur"):
                pool = path.split(".")[0]
                max_val = c.get(pool, {}).get("max")
                if max_val is None:
                    continue
                if not (0 <= new <= max_val):
                    problems.append(
                        f"delta #{i} char={char} {path}: "
                        f"{cur}{val:+d} -> {new} out of [0, {max_val}]"
                    )
    if problems:
        return {"item": "C-9.3", "verdict": "Major", "reason": "; ".join(problems)}
    return {
        "item": "C-9.3",
        "verdict": "通過",
        "reason": "All applied deltas keep hp.cur/mp.cur within [0, max].",
    }


def check_C9_6(deltas: list | None, status: dict) -> dict:
    """C-9.6: every delta.char is a known character in status.characters."""
    if not deltas:
        return {
            "item": "C-9.6",
            "verdict": "通過",
            "reason": "status_delta is empty.",
        }
    known = set(status.get("characters", {}))
    unknown = [str(d.get("char")) for d in deltas if d.get("char") not in known]
    if unknown:
        return {
            "item": "C-9.6",
            "verdict": "Major",
            "reason": (
                f"unknown char(s) in delta: {sorted(set(unknown))}. "
                f"known: {sorted(known)}."
            ),
        }
    return {
        "item": "C-9.6",
        "verdict": "通過",
        "reason": "All delta.char present in status.characters.",
    }


def check_C11_1(decision: dict | None, status: dict) -> dict:
    """C-11.1: each option's requires can be satisfied by the actor's state.

    Supported requires keys: mp, hp (integer thresholds against .cur),
    skill (name expected in .skills), level (>=). Unknown keys are ignored
    with a WARN log-line printed to stderr so they don't silently pass.
    """
    if not decision:
        return {
            "item": "C-11.1",
            "verdict": "通過",
            "reason": "no decision block.",
        }
    options = decision.get("options") or []
    default_char = decision.get("char", "H")
    problems: list[str] = []
    for opt in options:
        oid = opt.get("id", "?")
        char = opt.get("char", default_char)
        c = status.get("characters", {}).get(char)
        if c is None:
            problems.append(
                f"option {oid}: char={char} not in status.characters"
            )
            continue
        req = opt.get("requires") or {}
        for req_key, req_val in req.items():
            if req_key in ("mp", "hp"):
                cur = c.get(req_key, {}).get("cur", 0)
                if cur < req_val:
                    problems.append(
                        f"option {oid}: requires {req_key}>={req_val} "
                        f"but {char}.{req_key}.cur={cur}"
                    )
            elif req_key == "skill":
                skills = c.get("skills") or []
                if req_val not in skills:
                    problems.append(
                        f"option {oid}: requires skill={req_val!r} "
                        f"but {char}.skills={skills}"
                    )
            elif req_key == "level":
                lvl = c.get("level", 0)
                if lvl < req_val:
                    problems.append(
                        f"option {oid}: requires level>={req_val} "
                        f"but {char}.level={lvl}"
                    )
            else:
                sys.stderr.write(
                    f"[qa_deterministic] warning: option {oid} has unknown "
                    f"requires key {req_key!r}; skipped.\n"
                )
    if problems:
        return {
            "item": "C-11.1",
            "verdict": "Major",
            "reason": "; ".join(problems),
        }
    return {
        "item": "C-11.1",
        "verdict": "通過",
        "reason": "All option.requires satisfiable against canon.",
    }


def check_C11_3(decision: dict | None) -> dict:
    """C-11.3: option count within [2, 4].

    Following consistency_checklist.md's B1 gradation:
      n <= 1  -> Major   (no decision structure at all)
      2..4    -> 通過
      n >= 5  -> Warning (too many for readability)
    """
    if not decision:
        return {
            "item": "C-11.3",
            "verdict": "通過",
            "reason": "no decision block.",
        }
    options = decision.get("options") or []
    n = len(options)
    if 2 <= n <= 4:
        return {
            "item": "C-11.3",
            "verdict": "通過",
            "reason": f"option count={n} in [2, 4].",
        }
    if n <= 1:
        return {
            "item": "C-11.3",
            "verdict": "Major",
            "reason": f"option count={n} <= 1: not a decision.",
        }
    return {
        "item": "C-11.3",
        "verdict": "Warning",
        "reason": f"option count={n} > 4: too many for readability.",
    }


# ---------------------------------------------------------------------------
# HYBRID candidate extraction (Q2)
#
# These functions DO NOT judge. They cut small pieces out of the prose/meta so
# a later stage (Q3+) can ask an LLM the semantic question about each piece.
# Every function returns {item, candidates:[{snippet, meta}], needs_llm: True}.
# Code-confirmable facts (delta paths, field presence, bracket kind) are baked
# into `meta`; only the meaning judgment is left in the candidate.
# ---------------------------------------------------------------------------

# C-9.7 / C-10: concrete numeric mentions (HP/MP/level/digits).
NUMERIC_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("hp", re.compile(r"(?i)ＨＰ|HP")),
    ("mp", re.compile(r"(?i)ＭＰ|MP")),
    ("level", re.compile(r"(?i)レベル|ﾚﾍﾞﾙ|Lv\.?|level")),
    ("number", re.compile(r"[0-9０-９]+(?:\s*[/／]\s*[0-9０-９]+)?")),
]


def _attribution_hint(sentence: str) -> str:
    """Code-confirmable structural cue for C-10 attribution (LLM decides truth).

    monologue: 括弧書き独白（転生者の内語である可能性が高い＝帰属OKの候補）
    speech:    台詞（話者が現地人なら I-4 違反の候補）
    narration: 地の文（客観なら数値露出は違反の候補）
    """
    head = sentence.lstrip()[:1]
    if head in "（(":
        return "monologue"
    if head in "「『":
        return "speech"
    return "narration"


def extract_numeric_mentions(episode: str) -> dict:
    """C-9.7 / C-10: extract each concrete-number mention with ±1 sentence.

    The LLM later decides *whose perception* the number belongs to (H の内語 =
    OK, 現地人の視点/台詞 or 客観地の文 = I-4 違反). We only locate the mentions
    and hand over the surrounding small piece — never the whole episode.
    Qualitative expressions (深い傷／強そう) carry no digits and are skipped.
    """
    sentences = split_sentences(parse_episode_body(episode))
    candidates: list[dict] = []
    for i, sent in enumerate(sentences):
        cats: list[str] = []
        matched: list[str] = []
        for cat, pat in NUMERIC_PATTERNS:
            for m in pat.finditer(sent):
                cats.append(cat)
                matched.append(m.group(0))
        if not cats:
            continue
        ctx = sentences[max(0, i - 1) : i + 2]
        candidates.append(
            {
                "snippet": " ".join(ctx),
                "meta": {
                    "sentence": sent,
                    "categories": sorted(set(cats)),
                    "matched": matched,
                    "attribution_hint": _attribution_hint(sent),
                    "sentence_index": i,
                },
            }
        )
    return {"item": "C-9.7/C-10", "candidates": candidates, "needs_llm": True}


# C-11.2: 理干渉フラグ。requires が空（＝対価なし）で、label/intended_shift が
# 世界の根本律「理」に言及する option を、LLM への問い合わせ候補にする。
_RI_QUOTED = re.compile(r"[『「]理[』」]")
# 日常語の複合語は「理」の概念言及ではない（誤検出を減らす。最終判断は LLM）。
_RI_COMPOUNDS = (
    "無理", "料理", "整理", "管理", "心理", "論理", "理由", "理解", "処理",
    "修理", "地理", "物理", "受理", "代理", "調理", "倫理", "道理", "義理",
    "原理", "真理", "理性", "理想", "理論", "摂理", "合理", "理屈", "推理",
)


def _mentions_ri(text: str) -> tuple[bool, str | None]:
    """True if `text` references the world-law 理 (not a common compound)."""
    if not text:
        return (False, None)
    q = _RI_QUOTED.search(text)
    if q:
        return (True, q.group(0))
    for m in re.finditer("理", text):
        i = m.start()
        pair_back = text[max(0, i - 1) : i + 1]
        pair_fwd = text[i : i + 2]
        if pair_back in _RI_COMPOUNDS or pair_fwd in _RI_COMPOUNDS:
            continue
        return (True, "理")
    return (False, None)


def _requires_empty(opt: dict) -> bool:
    req = opt.get("requires")
    return not req  # None, missing, or {} all count as「対価なし」


def flag_ri_interference(decision: dict | None) -> dict:
    """C-11.2 candidate: options that break 理 with no required price.

    Code confirms two facts — (a) requires is empty, (b) label/intended_shift
    literally names 理 — and hands the option to the LLM, which decides whether
    it is truly an uncompensated 理破り (I-1 violation, Blocker). Options that
    carry a `requires` cost are NOT flagged here.
    """
    options = (decision or {}).get("options") or []
    candidates: list[dict] = []
    for opt in options:
        if not _requires_empty(opt):
            continue
        label = str(opt.get("label") or "")
        shift = str(opt.get("intended_shift") or "")
        ri_label, tok_l = _mentions_ri(label)
        ri_shift, tok_s = _mentions_ri(shift)
        if not (ri_label or ri_shift):
            continue
        candidates.append(
            {
                "snippet": label,
                "meta": {
                    "option_id": opt.get("id"),
                    "requires_empty": True,
                    "ri_in_label": ri_label,
                    "ri_in_intended_shift": ri_shift,
                    "ri_token": tok_l or tok_s,
                    "intended_shift": shift,
                    "ask": "対価なしに理を破る選択肢か（I-1 違反 = Blocker）",
                },
            }
        )
    return {"item": "C-11.2", "candidates": candidates, "needs_llm": True}


# C-9.1/C-9.2/C-9.4/C-12.3: pair each status_delta.cause with the prose event(s)
# that plausibly correspond, so the LLM can judge semantic consistency.
_KW_RE = re.compile(r"[一-龯々〆ヵヶ]+|[ァ-ヶーｦ-ﾟA-Za-z0-9]+")


def _keywords(text: str) -> list[str]:
    """Content-word candidates: kanji / katakana / latin-digit runs (drop kana particles)."""
    return _KW_RE.findall(text or "")


def extract_cause_pairs(deltas: list | None, episode: str) -> dict:
    """C-9.1/C-9.2/C-9.4/C-12.3: pair each delta.cause with prose-event snippets.

    Lexical overlap only proposes candidates; the LLM judges true correspondence
    (e.g. cause「魔物の爪」 vs prose「獣が…爪が肩を裂いた」). Code-confirmable facts
    for the semantic items are baked into meta:
      - is_mp_change / is_hp_change  → C-9.2 (魔法発動→MP消費), C-9.4 (死は死)
      - matched_keywords / score     → C-9.1 (cause の実在)
    A cause with no lexical match still yields one candidate (empty snippet) so
    the LLM is told to check for a missing/undescribed cause.
    """
    sentences = split_sentences(parse_episode_body(episode))
    candidates: list[dict] = []
    for idx, d in enumerate(deltas or []):
        cause = str(d.get("cause") or "")
        change = d.get("change") or {}
        paths = [resolve_path(str(k)) for k in change.keys()]
        meta_common = {
            "delta_index": idx,
            "char": d.get("char"),
            "cause": cause,
            "change": change,
            "is_mp_change": any(p == "mp.cur" for p in paths),
            "is_hp_change": any(p == "hp.cur" for p in paths),
        }
        kws = _keywords(cause)
        scored: list[tuple[int, int, str, list[str]]] = []
        for j, sent in enumerate(sentences):
            hit = [k for k in kws if k in sent]
            if not hit:
                continue
            scored.append((sum(len(k) for k in hit), j, sent, hit))
        scored.sort(key=lambda t: (-t[0], t[1]))
        top = scored[:3]
        if top:
            for score, _j, sent, hit in top:
                m = dict(meta_common)
                m["matched_keywords"] = hit
                m["score"] = score
                candidates.append({"snippet": sent, "meta": m})
        else:
            m = dict(meta_common)
            m["matched_keywords"] = []
            m["score"] = 0
            m["note"] = "no lexical match in prose; cause実在(C-9.1) を LLM で要確認"
            candidates.append({"snippet": "", "meta": m})
    return {
        "item": "C-9.1/C-9.2/C-9.4/C-12.3",
        "candidates": candidates,
        "needs_llm": True,
    }


def extract_all(meta: dict, episode_text: str) -> dict:
    """Run every HYBRID extractor and return the structured candidate bundle."""
    return {
        "numeric": extract_numeric_mentions(episode_text),
        "ri_interference": flag_ri_interference(meta.get("decision")),
        "cause_pairs": extract_cause_pairs(meta.get("status_delta"), episode_text),
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


CODE_ITEMS = ["C-9.3", "C-9.6", "C-11.1", "C-11.3"]


def check_all(meta: dict, status: dict) -> list[dict]:
    deltas = meta.get("status_delta")
    decision = meta.get("decision")
    return [
        check_C9_3(deltas, status),
        check_C9_6(deltas, status),
        check_C11_1(decision, status),
        check_C11_3(decision),
    ]


def read_file(p: str | Path) -> str:
    return Path(p).read_text(encoding="utf-8")


def print_verdicts(label: str, verdicts: list[dict]) -> None:
    print(f"===== {label} =====")
    for v in verdicts:
        print(f"  {v['item']:8s}  {v['verdict']:8s}  — {v['reason']}")


# --- Regression --------------------------------------------------------------

REGRESSION_CASES: list[tuple[str, dict]] = [
    (
        "story/ep-00-b1test.md",
        {
            "C-9.3": "通過",
            "C-9.6": "通過",
            "C-11.1": "通過",
            "C-11.3": "通過",
        },
    ),
    (
        "story/ep-00-b1test-violation.md",
        {
            "C-9.3": "通過",
            "C-9.6": "通過",
            "C-11.1": "Major",   # Option B: requires mp:5 vs cur mp:2
            "C-11.3": "通過",     # 4 options is in [2, 4] per current spec
        },
    ),
]


def regression(status_path: str = "canon/status.yaml") -> int:
    status = parse_status(read_file(status_path))
    all_ok = True
    for ep_path, expected in REGRESSION_CASES:
        meta = parse_episode_meta(read_file(ep_path))
        verdicts = check_all(meta, status)
        print_verdicts(ep_path, verdicts)
        for v in verdicts:
            exp = expected.get(v["item"])
            ok = v["verdict"] == exp
            mark = "OK  " if ok else "MISS"
            print(f"    [{mark}] {v['item']}: got={v['verdict']}, expected={exp}")
            if not ok:
                all_ok = False
        print()
    print("REGRESSION:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


# --- Hybrid extraction regression (Q2) --------------------------------------


def regression_hybrid(status_path: str = "canon/status.yaml") -> int:
    """Q2 sanity checks for the HYBRID extractors (extraction only, no judging)."""
    all_ok = True

    def check(name: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        print(f"    [{'OK  ' if ok else 'MISS'}] {name}: {detail}")
        if not ok:
            all_ok = False

    print("===== HYBRID extraction (Q2) =====")

    # 1) B1 violation: 理干渉フラグが「対価なしの理破り」option(D) に立つ。
    v_meta = parse_episode_meta(read_file("story/ep-00-b1test-violation.md"))
    v_ri = flag_ri_interference(v_meta.get("decision"))
    flagged = [c["meta"]["option_id"] for c in v_ri["candidates"]]
    check(
        "b1test-violation flag_ri_interference",
        flagged == ["D"],
        f"flagged options={flagged} (expected ['D'])",
    )

    # 2) B1 correct: 理干渉フラグは立たない（誤検出なし）。
    c_meta = parse_episode_meta(read_file("story/ep-00-b1test.md"))
    c_ri = flag_ri_interference(c_meta.get("decision"))
    check(
        "b1test flag_ri_interference",
        c_ri["candidates"] == [],
        f"flagged options={[c['meta']['option_id'] for c in c_ri['candidates']]} (expected [])",
    )

    # 3) A3: 数値言及を漏れなく抽出（HP と MP の両方が候補に出る）。
    a3_text = read_file("story/ep-00-a3test.md")
    a3_num = extract_numeric_mentions(a3_text)
    a3_cats = {c for cand in a3_num["candidates"] for c in cand["meta"]["categories"]}
    check(
        "a3test extract_numeric_mentions",
        {"hp", "mp"} <= a3_cats,
        f"n={len(a3_num['candidates'])} categories={sorted(a3_cats)} (expect hp & mp)",
    )

    # 4) A2: 本文に具体数値が無い話では候補ゼロ（過剰抽出しない）。
    a2_text = read_file("story/ep-00-a2test.md")
    a2_num = extract_numeric_mentions(a2_text)
    check(
        "a2test extract_numeric_mentions",
        len(a2_num["candidates"]) == 0,
        f"n={len(a2_num['candidates'])} (expected 0; digits live only in status_delta meta)",
    )

    # 5) A2: cause↔本文事象のペアが各 delta に付く。
    a2_pairs = extract_cause_pairs(a2_meta_deltas(a2_text), a2_text)
    delta_idxs = sorted({c["meta"]["delta_index"] for c in a2_pairs["candidates"]})
    check(
        "a2test extract_cause_pairs",
        delta_idxs == [0, 1],
        f"delta_indexes covered={delta_idxs} (expected [0, 1])",
    )

    print()
    print("HYBRID REGRESSION:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


def a2_meta_deltas(a2_text: str) -> list:
    return parse_episode_meta(a2_text).get("status_delta") or []


# --- CLI --------------------------------------------------------------------


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic (CODE-only) QA for sdnd-ordia."
    )
    ap.add_argument(
        "episode",
        nargs="?",
        help="path to episode .md file (omit if --regression)",
    )
    ap.add_argument(
        "--status",
        default="canon/status.yaml",
        help="path to canon/status.yaml (default: canon/status.yaml)",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="emit JSON to stdout instead of a table",
    )
    ap.add_argument(
        "--extract",
        action="store_true",
        help="emit HYBRID candidate extraction (Q2) as JSON; no CODE verdicts",
    )
    ap.add_argument(
        "--regression",
        action="store_true",
        help="run built-in CODE + HYBRID regression fixtures",
    )
    args = ap.parse_args(argv)

    if args.regression:
        code_rc = regression(args.status)
        print()
        hybrid_rc = regression_hybrid(args.status)
        return code_rc or hybrid_rc

    if not args.episode:
        ap.error("episode is required (or use --regression)")

    meta = parse_episode_meta(read_file(args.episode))

    # Q2: extraction only — cut small pieces for a later LLM stage, no judging.
    if args.extract:
        bundle = extract_all(meta, read_file(args.episode))
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    status = parse_status(read_file(args.status))
    verdicts = check_all(meta, status)
    if args.json:
        print(json.dumps(verdicts, ensure_ascii=False, indent=2))
    else:
        print_verdicts(args.episode, verdicts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
