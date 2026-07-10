"""village.py — 村の探索フェーズ（★5 つから 3 つ選ぶ）.

選択のたびに **d6 を 1 回消費する**（値は使わないが、これにより後続の判定が
seed 直結でなくなる＝探索の並びが乱数列をずらす）。固定テキストは Ordia の
世界観に沿う（数行）。数値ボーナスは H の内心にだけ映る（I-4）。
"""

from __future__ import annotations

from .rng import d6

# key -> (表示名, gain 文言（ログに残す）, 固定描写, ボーナス適用関数)
# ボーナス適用関数は GameState を受け取り、フラグ/持ち物を立てる。

EXPLORE_ORDER = ["elder", "herbs", "shrine", "well", "scout"]


def _apply_elder(st):
    st.elder = True


def _apply_herbs(st):
    st.herbs += 2


def _apply_shrine(st):
    st.blessing = True


def _apply_well(st):
    st.dagger = True


def _apply_scout(st):
    st.scout = True


EXPLORE = {
    "elder": {
        "name": "村長に詳しく聞く",
        "gain": "頭目への命中 +2",
        "text": (
            "村長は囲炉裏の灰を掻き、頭目の癖を低く語る。"
            "「あれは右へ躱す。左を突け」——H の内心に、頭目への一手が刻まれる。"
        ),
        "apply": _apply_elder,
    },
    "herbs": {
        "name": "薬草の女を訪ねる",
        "gain": "薬草 ×2（戦闘中に使用）",
        "text": (
            "薬草の女は乾いた葉を二包み、H の掌に押しつける。"
            "「傷が深くなったら噛みなさい。苦いが、閉じる」。"
        ),
        "apply": _apply_herbs,
    },
    "shrine": {
        "name": "古い祠に祈る",
        "gain": "祝福：全命中判定 +1",
        "text": (
            "苔むした祠に手を合わせる。名も知れぬ古い神の気配が、"
            "H の指先をわずかに落ち着かせる——狙いが、ぶれにくくなる。"
        ),
        "apply": _apply_shrine,
    },
    "well": {
        "name": "井戸を調べる",
        "gain": "錆びた短剣：物理ダメージ +2",
        "text": (
            "涸れた井戸の底に、錆びた短剣が沈んでいた。"
            "刃こぼれてはいるが、素手よりはずっと深く届く。"
        ),
        "apply": _apply_well,
    },
    "scout": {
        "name": "森を偵察する",
        "gain": "藪ルート自動成功 / 見張りへの初撃が必中",
        "text": (
            "H は日暮れ前の森を一巡りする。藪の抜け道と、見張りの立つ角を覚えた。"
            "最初の一撃は、外さない。"
        ),
        "apply": _apply_scout,
    },
}


def explore(state, key: str) -> None:
    """探索を 1 つ実行する。d6 を 1 回消費し、ボーナスを適用し、explore を記録する。"""
    opt = EXPLORE[key]
    d6(state.rng)                 # ★選択のたびに d6 を 1 回消費（値は使わない）
    opt["apply"](state)
    state.emit(type="explore", place=key, gain=opt["gain"])
