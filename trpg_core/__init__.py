"""trpg_core — LLM を一切呼ばない決定論的 TRPG エンジン（sdnd-ordia, Step T / T0）.

設計の核:
  - **乱数はコードが独占する**（mulberry32 相当の seeded PRNG）。LLM に振らせない。
  - **自由度 0**。プレイヤーは用意された選択肢と戦闘コマンドしか選べない。
  - **描写は固定テキスト**（scenario.py / village.py）。writer/director/QA は使わない。
  - **seed 固定 → 完全再現**。同じ seed・同じ入力列なら常に同じログを吐く。

Ordia の invariants を尊重:
  - I-2: 魔法は MP を消費する。MP 不足なら選べない（C-11.1 と同じ論理）。
  - I-4: 数値・ステータスは転生者 H の内心としてのみ提示する。
  - I-1: 理を破る選択肢を作らない。

このパッケージは canon/ qa/ specs/ meta/ を **読むだけ**で、書き換えない。
resolve.py は参照してよいが、この engine は独自の成否二択判定式を使う。
"""

from .rng import Rng, d6

__all__ = ["Rng", "d6"]
