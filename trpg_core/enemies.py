"""enemies.py — 敵の *構造*（データではなく器）.

敵の数値（HP / 攻撃修正 / ダメージ範囲 / 命中目標値）は **シナリオ(YAML)** に持たせ、
`scenario_loader.Scenario.make_enemy()` が組み立てる。ここに残すのは Enemy の形だけ。
（市販の数表・固有名詞はコピーしない。数値は各シナリオが自前で持つ。）
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Enemy:
    key: str            # ログ・内部識別（"sentry"/"goblin"/"chief" 等）
    name_ja: str        # コンソール表示（H の内心に映る像）
    hp: int
    atk: int            # 命中修正
    dmg_lo: int
    dmg_hi: int
    player_target: int  # プレイヤーがこの敵に当てるための目標値
    hp_max: int | None = None

    def __post_init__(self) -> None:
        if self.hp_max is None:
            self.hp_max = self.hp

    @property
    def alive(self) -> bool:
        return self.hp > 0
