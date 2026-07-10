"""simulate.py — 勝率シミュレータ（ヘッドレス自動プレイ）.

N セッションを seed を変えて自動プレイし、探索ビルド別の勝率を出す。LLM 不使用。
policy（PolicyController）: HP<=7 かつ薬草あり → herb / MP>=2 → magic / else attack。

    python -m trpg_core.simulate --n 200
"""

from __future__ import annotations

import argparse
import io
import sys

from .session import run_policy

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BUILDS = [
    ["elder", "shrine", "herbs"],
    ["elder", "well", "shrine"],
    ["scout", "herbs", "elder"],
    ["well", "scout", "shrine"],
]


def simulate_build(build, n, seed0=0):
    wins = 0
    turns_sum = 0
    hp_min_sum = 0
    for i in range(n):
        seed = seed0 + i
        result, state = run_policy(seed, build)
        if result == "clear":
            wins += 1
        turns_sum += state.log[-1]["t"]
        # 到達した最小 player_hp（削られ具合）
        hp_vals = [e["player_hp"] for e in state.log if e["type"] == "enemy_attack"]
        hp_min_sum += min(hp_vals) if hp_vals else state.hp
    return {
        "build": build,
        "n": n,
        "wins": wins,
        "rate": wins / n if n else 0.0,
        "avg_turns": turns_sum / n if n else 0.0,
        "avg_min_hp": hp_min_sum / n if n else 0.0,
    }


def main(argv):
    ap = argparse.ArgumentParser(description="決定論 TRPG 勝率シミュレータ（LLM 不使用）。")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed0", type=int, default=0, help="開始 seed（seed0..seed0+n-1 を回す）")
    args = ap.parse_args(argv)

    print(f"===== 勝率シミュレーション（N={args.n} / seed {args.seed0}..{args.seed0 + args.n - 1}）=====")
    print(f"{'build':30s} {'win%':>6s} {'wins':>7s} {'avg_turns':>10s} {'avg_min_hp':>11s}")
    for build in BUILDS:
        r = simulate_build(build, args.n, args.seed0)
        label = "+".join(build)
        print(f"{label:30s} {r['rate']*100:5.1f}% {r['wins']:4d}/{r['n']:<3d} "
              f"{r['avg_turns']:10.1f} {r['avg_min_hp']:11.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
