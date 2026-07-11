"""village.py — 村（出立前）の探索フェーズの *進行制御*（エンジン側）.

探索の中身（選択肢・効果・固定テキスト）は **シナリオ(YAML)** の `village:` にある。
ここに残すのは「進行の仕組み」だけ:
  - 選択のたびに **d6 を 1 回消費する**（値は使わないが、探索の並びが後続の乱数列を
    ずらす＝seed 直結でなくする）。この消費は不変（回帰の基盤）。
  - 効果の *適用*（宣言 → state への反映）。宣言はシナリオ、適用はエンジン。

数値ボーナスは H の内心にだけ映る（I-4）。
"""

from __future__ import annotations

from .rng import d6


def apply_effect(state, effect: dict | None) -> None:
    """effect 宣言をエンジンが解釈して state に反映する。
    item は state.herbs へ畳み込む。受動効果は state.effects に積み、
    命中/ダメージ/偵察の判定時に rules の effect_* / has_recon が解釈する。"""
    if not effect:
        return
    etype = effect.get("type")
    if etype == "item":
        if effect.get("item") == "herb":
            state.herbs += int(effect.get("count", 0))
        # 他アイテム種別を足すときはここに分岐を追加（＝エンジンを触る）
    else:
        # hit_bonus / damage_bonus / recon などの受動効果
        state.effects.append(dict(effect))


def explore(state, key: str) -> None:
    """探索を 1 つ実行する。d6 を 1 回消費し、効果を適用し、explore を記録する。"""
    opt = state.scenario.village_option(key)
    d6(state.rng)                                  # ★選択のたびに d6 を 1 回消費（不変）
    apply_effect(state, opt.get("effect"))
    state.buff_labels.append(opt.get("name", key))  # 内心表示用（ログには出ない）
    state.emit(type="explore", place=key, gain=opt.get("gain", ""))
