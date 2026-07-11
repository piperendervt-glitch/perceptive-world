"""map_view.py — テキスト地図（★ビュー）.

GameMap（真実源）を **読むだけ** で描く純粋なビュー。地図データは書き換えない。
後で LOD 版ビュー（解像度・痕跡）を足すときは、この render_* を差し替えるだけでよい
（真実源 GameMap の形は変えない）。判定も乱数も触らない。

現在地を中心に、東西南北の出口と行き先名を十字で示す:

              [古井戸]
                ↑北
    [村長の家] ←  >村の広場<  → [薬草小屋]
                ↓南
              [古い祠]
"""

from __future__ import annotations

import unicodedata

_CARDINALS = ("north", "south", "east", "west")


def _dwidth(s: str) -> int:
    """端末上の表示幅（CJK 全角=2, その他=1）。十字の中央寄せに使う。"""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _pad(target_col: int, s: str) -> str:
    return " " * max(0, target_col) + s


def render_map(gm) -> str:
    """現在地を強調した十字地図の文字列を返す（純粋関数・副作用なし）。"""
    here = gm.here()
    center = f">{here.name}<"
    west = gm.dest_name("west")
    east = gm.dest_name("east")
    north = gm.dest_name("north")
    south = gm.dest_name("south")

    left = f"[{west}] ← " if west else ""
    right = f" → [{east}]" if east else ""
    mid = f"{left}{center}{right}"

    # 中央セル（>current<）の開始桁と幅。北/南の名札をこの上に中央寄せする。
    center_start = _dwidth(left)
    center_w = _dwidth(center)

    def _centered(label: str) -> str:
        col = center_start + max(0, (center_w - _dwidth(label)) // 2)
        return _pad(col, label)

    lines: list[str] = []
    if north:
        lines.append(_centered(f"[{north}]"))
        lines.append(_centered("↑北"))
    lines.append(mid)
    if south:
        lines.append(_centered("↓南"))
        lines.append(_centered(f"[{south}]"))
    return "\n".join(lines)


def render_exits(gm) -> str:
    """出口の一覧（十字に載らない方角も拾える保険のビュー）。"""
    ex = gm.here().exits
    jp = {"north": "北", "south": "南", "east": "東", "west": "西"}
    parts = []
    for d, dest in ex.items():
        label = jp.get(d, d)
        parts.append(f"{label}→{gm.locations[dest].name}")
    return "  出口: " + (" / ".join(parts) if parts else "なし")
