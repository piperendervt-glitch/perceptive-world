"""rng.py — mulberry32 相当の seeded PRNG（★JavaScript から厳密移植）.

乱数列が JS 版と一致しないと seed=7 の参照ログとの回帰が通らない。**32bit 演算**に注意
（Python の int は多倍長なので、各段で & 0xFFFFFFFF を挟んで 32bit に畳む）。

    class Rng:
        def next(self) -> float:  # [0, 1)
    d6(rng) -> int  # floor(next()*6)+1、面 1..6

乱数はコードが独占する（[[../CLAUDE.md]] D1 の原則）。LLM には振らせない。
"""

from __future__ import annotations

_U32 = 0xFFFFFFFF
_INC = 0x6D2B79F5  # mulberry32 の増分定数


class Rng:
    """mulberry32。内部状態は 32bit の self.a のみ（save/load はこれを保存すれば足りる）。"""

    __slots__ = ("a",)

    def __init__(self, seed: int):
        self.a = seed & _U32

    def next(self) -> float:
        """[0, 1) の float を 1 つ返し、状態を 1 つ進める。JS mulberry32 と同一列。"""
        self.a = (self.a + _INC) & _U32
        t = self.a
        t = (t ^ (t >> 15)) * (t | 1) & _U32
        t ^= (t + ((t ^ (t >> 7)) * (t | 61) & _U32)) & _U32
        return ((t ^ (t >> 14)) & _U32) / 4294967296

    # --- 再現用の内部状態（save/load 用） ---
    def state(self) -> int:
        return self.a

    def set_state(self, a: int) -> None:
        self.a = a & _U32


def d6(rng: Rng) -> int:
    """1D6。floor(next()*6)+1。乱数は 1 回だけ消費する。"""
    return int(rng.next() * 6) + 1
