"""scenario.py — ノードグラフ ＋ 固定テキスト（描写は LLM ではなく定数）.

    [村] 探索3つ → 森へ発つ
      forest 森の道
        ├ 街道を行く          → cave_entrance
        └ 藪を抜ける【vit 8】  → sneak_ok / sneak_fail → cave_entrance
      cave_entrance 洞窟の入口 : 戦闘[sentry] → cave_hall
      cave_hall 洞窟・広間
        ├ 正面から進む          → hall2 : 戦闘[goblin, goblin]
        └ 松明を消して忍ぶ【vit 8, 偵察 +2】 → 成功 hall1[goblin] / 失敗 hall2[goblin,goblin]
      depths 洞窟・最奥 : 戦闘[chief, goblin] → win
      win 帰還（エンディング）
      defeat 村・広場で目覚め → forest へ戻れる

ラベル文言はログの choice.label と一致させる（回帰の基盤）。
"""

from __future__ import annotations

# --- ノード描写（H の視点。固定テキスト） ---
NODE_TEXT = {
    "forest": (
        "村の柵を抜けると、森の道が二手に分かれていた。踏み固められた街道と、"
        "棘の藪に呑まれかけた細道。頭目の塒は、この森の奥の洞窟にあるという。"
    ),
    "sneak_ok": (
        "藪を縫って、見張りの目を掠めた。棘が頬を裂いたが、誰にも見咎められていない。"
        "洞窟の入口は、もう目の前だ。"
    ),
    "sneak_fail": (
        "藪で足を取られ、枝が高く鳴った。見張りが気配を探る——が、H は物陰へ滑り込む。"
        "露見はしていない。ともかく、洞窟の入口へ。"
    ),
    "cave_entrance": (
        "洞窟の入口に、見張りのゴブリンが一体。松明の油煙が鼻をつく。"
        "抜けねば、奥へは進めない。"
    ),
    "cave_hall": (
        "入口を抜けると、広間に出た。奥へ続く道は二つ——正面の開けた通路と、"
        "松明の列に沿った暗がり。"
    ),
    "hall1": (
        "暗がりを縫って進むと、ゴブリンが一体、こちらに気づいて牙を剥いた。",
    ),
    "hall2": (
        "開けた通路の先、ゴブリンが二体、同時に立ち上がる。",
    ),
    "depths": (
        "最奥の広間。頭目が背の高い椅子から立ち上がり、傍らのゴブリンが身構える。"
        "村長の言葉が、H の内心を過ぎる——「あれは右へ躱す。左を突け」。"
    ),
    "win": (
        "頭目は崩れ落ち、洞窟に静けさが戻った。H は夜の森を抜け、村の灯へ帰る。"
        "礼を言う村人たちの中で、H だけが、掌に残る数値の余韻を見ていた。"
    ),
    "defeat": (
        "気づくと、村の広場だった。誰かが H を運び戻したらしい。"
        "傷は浅く塞がれ、息が整う。まだ、終わってはいない。"
    ),
}

# --- 選択肢ラベル（ログ label と一致） ---
FOREST_CHOICES = [
    ("road", "街道を行く"),
    ("bush", "藪を抜ける【vit 判定 / 目標 8】"),
]
SNEAK_CONTINUE = [("cave", "洞窟へ")]
CAVE_HALL_CHOICES = [
    ("front", "正面から進む"),
    ("sneak", "松明を消して忍ぶ【vit 判定 / 目標 8】"),
]

# --- 判定目標値 ---
SNEAK_TARGET = 8       # forest 藪 / cave_hall 松明 とも vit 目標 8
FLEE_TARGET = 8        # 離脱

# --- 戦闘ノード → 勝利後の遷移先 ---
COMBAT_NEXT = {
    "cave_entrance": "cave_hall",
    "hall1": "depths",
    "hall2": "depths",
    "depths": "win",
}

# --- 戦闘ノードの敵編成 ---
COMBAT_ENEMIES = {
    "cave_entrance": ["sentry"],
    "hall1": ["goblin"],
    "hall2": ["goblin", "goblin"],
    "depths": ["chief", "goblin"],
}


def node_text(node: str) -> str:
    t = NODE_TEXT.get(node, "")
    if isinstance(t, tuple):
        return t[0]
    return t
