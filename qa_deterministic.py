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
        "--regression",
        action="store_true",
        help="run built-in B1 regression fixtures",
    )
    args = ap.parse_args(argv)

    if args.regression:
        return regression(args.status)

    if not args.episode:
        ap.error("episode is required (or use --regression)")

    status = parse_status(read_file(args.status))
    meta = parse_episode_meta(read_file(args.episode))
    verdicts = check_all(meta, status)
    if args.json:
        print(json.dumps(verdicts, ensure_ascii=False, indent=2))
    else:
        print_verdicts(args.episode, verdicts)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
