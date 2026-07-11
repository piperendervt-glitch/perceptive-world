"""map.py — 村の空間構造（★真実源）.

**設計思想**（trace-world の「World が真実源、describe はビュー」と同型）:
  - 地図は「世界の空間構造」というデータ。テキスト表示は map_view.py の *ビュー*。
  - 真実源（この GameMap）はどの解像度・痕跡でも同じ。表示だけ差し替えれば拡張できる:
      Step 10（地図LOD）  : Location に resolution を足す（遠い場所は名前だけ）。
      Step 11（痕跡LOD）  : Location に trace_level を足す（訪れた場所ほど詳細）。
  - **物語ノード（scenario の nodes＝進行）** と **地図ロケーション（探索可能な空間）**
    を区別する。今回は「村」を地図化する（本編ノードは地図化しない）。

現在地(current)はゲーム状態なので GameState.location に永続化する（save/load 対象）。
このモジュールは判定も乱数も一切触らない（空間構造とその走査だけ）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Location:
    id: str
    name: str
    exits: dict = field(default_factory=dict)   # {方角: 行き先 location_id}
    action: str | None = None                   # ここで行える探索アクションの key（village option）
    leads_to_adventure: bool = False            # ここから本編（forest ノード）へ発てる
    # --- 将来の器（今は使わない・拡張点だけ明示：YAGNI だが構造は空けておく）---
    # resolution: float = 1.0   # Step 10: 地図LOD（遠い場所ほど粗く＝名前だけ）
    # trace_level: float = 0.0  # Step 11: 痕跡LOD（訪れた場所ほど詳細に描く）


class GameMap:
    """ロケーション集合（静的）＋現在地（動的）。移動と出口の照会だけを持つ。"""

    def __init__(self, locations: dict[str, Location], current: str):
        self.locations = locations
        self.current = current

    def here(self) -> Location:
        return self.locations[self.current]

    def exits(self) -> dict:
        """現在地の出口 {方角: 行き先id} のコピー。"""
        return dict(self.here().exits)

    def dest_name(self, direction: str) -> str | None:
        """方角の先のロケーション名（無ければ None）。ビューが使う読み取り専用照会。"""
        ex = self.here().exits
        if direction not in ex:
            return None
        return self.locations[ex[direction]].name

    def move(self, direction: str) -> bool:
        """方角で移動する。出口があれば current を更新して True、無ければ False。"""
        ex = self.here().exits
        if direction in ex:
            self.current = ex[direction]
            return True
        return False


def build_map(scenario, current: str | None = None) -> GameMap:
    """シナリオの map セクション（データ）から GameMap（真実源）を構築する。"""
    locations: dict[str, Location] = {}
    for lid, ld in scenario.map_locations.items():
        locations[lid] = Location(
            id=lid,
            name=ld["name"],
            exits=dict(ld.get("exits", {})),
            action=ld.get("action"),
            leads_to_adventure=bool(ld.get("leads_to_adventure", False)),
        )
    return GameMap(locations, current or scenario.map_start)
