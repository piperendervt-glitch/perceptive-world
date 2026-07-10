"""enemies.py — 敵データ（自前の数値。市販の数表・固有名詞はコピーしない）.

| key    | 表示名           | HP | atk | dmg | player_target |
|--------|------------------|----|-----|-----|---------------|
| sentry | 見張りゴブリン   |  5 | +0  | 1-2 | 6             |
| goblin | ゴブリン         |  5 | +0  | 1-2 | 6             |
| chief  | ゴブリンの頭目   | 18 | +2  | 2-5 | 8             |
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Enemy:
    key: str            # ログ・内部識別（"sentry"/"goblin"/"chief"）
    name_ja: str        # コンソール表示（H の内心に映る像）
    hp: int
    atk: int            # 命中修正
    dmg_lo: int
    dmg_hi: int
    player_target: int  # プレイヤーがこの敵に当てるための目標値

    @property
    def alive(self) -> bool:
        return self.hp > 0


_TEMPLATES = {
    "sentry": ("見張りゴブリン", 5, 0, 1, 2, 6),
    "goblin": ("ゴブリン", 5, 0, 1, 2, 6),
    "chief": ("ゴブリンの頭目", 18, 2, 2, 5, 8),
}


def make_enemy(key: str) -> Enemy:
    name_ja, hp, atk, lo, hi, pt = _TEMPLATES[key]
    return Enemy(key=key, name_ja=name_ja, hp=hp, atk=atk, dmg_lo=lo, dmg_hi=hi, player_target=pt)


def make_group(keys: list[str]) -> list[Enemy]:
    return [make_enemy(k) for k in keys]
