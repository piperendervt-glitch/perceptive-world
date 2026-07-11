"""scenario_loader.py — シナリオ(YAML)を読み、エンジンが走査する内部表現へ変換する.

**分離の線**:
  - シナリオ（このファイルが読む *データ*）: ノード構造・選択肢・判定の目標値・
    戦闘遭遇・敵ステータス・探索・効果の「宣言」・キャラ初期値・クリア/敗北ノード。
  - エンジン（trpg_core の *仕組み*）: 2D6 判定・乱数(Rng)・修正値の式・戦闘解決・
    セーブ/ロード・ノードグラフ走査・**効果の適用ロジック**（effect.type を解釈）。

このローダーは「宣言」を構造化するだけで、判定も適用もしない。scenarios/ 配下の
ファイルを差し替えれば別のシナリオが走る。LLM は使わない。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

from .enemies import Enemy

SCENARIO_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "scenarios")


@dataclass
class Choice:
    key: str                      # コントローラが選ぶ内部キー（ログには出ない）
    label: str                    # ログ choice.label と一致
    next: str | None = None       # 直行き遷移先
    check: dict | None = None     # 判定つき遷移（{stat,target,tag,recon_auto,recon_bonus}）
    on_success: str | None = None
    on_failure: str | None = None


@dataclass
class Node:
    id: str
    kind: str                     # "decision" | "combat" | "ending"
    title: str = ""
    text: list = field(default_factory=list)
    # decision
    choices: list = field(default_factory=list)
    # combat
    encounter: list = field(default_factory=list)
    recon_free_first: bool = False
    on_win: str | None = None
    # ending / defeat
    ending: str | None = None
    on_defeat_return: str | None = None


class Scenario:
    """1 本のシナリオ。エンジンが参照する読み取り専用のビュー。"""

    def __init__(self, data: dict):
        m = data.get("meta", {})
        self.id = m.get("id", "?")
        self.title = m.get("title", "")
        self.intro = m.get("intro", "")

        ch = data["character"]
        attrs = ch["attributes"]
        self.character = {
            "hp_max": int(ch["hp"]),
            "mp_max": int(ch["mp"]),
            "str": int(attrs["str"]),
            "mag": int(attrs["mag"]),
            "vit": int(attrs["vit"]),
        }

        v = data["village"]
        self.village_pick_count = int(v["pick_count"])
        self.village_options = [dict(o) for o in v["options"]]     # 宣言のまま保持
        self.village_order = [o["key"] for o in self.village_options]
        self._village_by_key = {o["key"]: o for o in self.village_options}

        self.enemies: dict[str, dict] = {}
        for key, e in data["enemies"].items():
            lo, hi = e["dmg"]
            self.enemies[key] = {
                "name": e["name"], "hp": int(e["hp"]), "atk": int(e["atk"]),
                "dmg_lo": int(lo), "dmg_hi": int(hi), "target": int(e["target"]),
            }

        self.start_node = data["start_node"]
        self.nodes: dict[str, Node] = {}
        for nid, nd in data["nodes"].items():
            self.nodes[nid] = self._build_node(nid, nd)

        # 村の空間構造（任意）。無ければ従来のリスト選択にフォールバックする。
        mp_data = data.get("map")
        if mp_data:
            self.has_map = True
            self.map_start = mp_data["start"]
            self.map_locations = {lid: dict(ld) for lid, ld in mp_data["locations"].items()}
        else:
            self.has_map = False
            self.map_start = None
            self.map_locations = {}

    @staticmethod
    def _build_node(nid: str, nd: dict) -> Node:
        if "choices" in nd:
            kind = "decision"
        elif "encounter" in nd:
            kind = "combat"
        else:
            kind = "ending"
        choices = [
            Choice(
                key=c["key"], label=c["label"], next=c.get("next"),
                check=c.get("check"),
                on_success=c.get("on_success"), on_failure=c.get("on_failure"),
            )
            for c in nd.get("choices", [])
        ]
        return Node(
            id=nid, kind=kind, title=nd.get("title", ""),
            text=list(nd.get("text", [])), choices=choices,
            encounter=list(nd.get("encounter", [])),
            recon_free_first=bool(nd.get("recon_free_first", False)),
            on_win=nd.get("on_win"), ending=nd.get("ending"),
            on_defeat_return=nd.get("on_defeat_return"),
        )

    # --- アクセサ（エンジンはここ越しにだけシナリオを見る） ---
    def node(self, nid: str) -> Node:
        return self.nodes[nid]

    def node_text(self, nid: str) -> str:
        n = self.nodes.get(nid)
        return "".join(n.text) if n else ""

    def village_option(self, key: str) -> dict:
        return self._village_by_key[key]

    def make_enemy(self, key: str) -> Enemy:
        e = self.enemies[key]
        return Enemy(key=key, name_ja=e["name"], hp=e["hp"], atk=e["atk"],
                     dmg_lo=e["dmg_lo"], dmg_hi=e["dmg_hi"], player_target=e["target"])

    def make_group(self, keys: list[str]) -> list[Enemy]:
        return [self.make_enemy(k) for k in keys]

    def enemy_name(self, key: str) -> str:
        e = self.enemies.get(key)
        return e["name"] if e else key

    def ending_text(self, result: str) -> str:
        """終局(result)に対応するノードの固定テキスト。
        clear なら ending==clear のノード、defeat なら on_defeat_return を持つノード。"""
        for n in self.nodes.values():
            if result == "clear" and n.ending == "clear":
                return "".join(n.text)
            if result == "defeat" and n.on_defeat_return:
                return "".join(n.text)
        return ""


def load_scenario(scenario_id: str = "goblin") -> Scenario:
    """scenarios/<id>.yaml を読み込んで Scenario を返す。"""
    path = os.path.join(SCENARIO_DIR, f"{scenario_id}.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario(data)
