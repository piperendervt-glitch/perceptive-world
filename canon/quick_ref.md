# quick_ref.md — canon 最新要約（TIER1・常時参照）

書込許可: editor のみ。
このファイルは**常時ロード**されるため、常に短く保つ。詳細は canon/active/ に置く。

## 現況（A1: 数値の真実源シード済み。本編は未着手）

- 本編未着手。canon に登録されたエピソード事実はまだない。
- 世界設定・キャラクター・対立・中心の問いは specs/core/* を参照。
- M2 で第1話を執筆し、editor がここに最新要約を書き始める。

## 主人公 H の現在ステータス（canon/status.yaml より）

- H: Lv1 / HP 10/20 / MP 2/10 / str 8, mag 8, vit 9 / skills: なし / buffs・debuffs: なし
- 可視範囲: 転生者のみ（I-4）。他転生者（K/R/S）と NPC の数値は未定義（存在させない）。
- 直近の変動: ep-00-a2test（検証話・canon 未登録）で灯火 → mp -8、爪傷 → hp -10。クリップ発生なし。

## フォーマット（M2 以降で使用）

```
## 最新話: ep-XX
- 出来事の一行要約
- 生じた事実（who did what）
- 発生した「失った」もの
- 開いたままの問い（open_questions と連動）

## 継続中の対立
- H × K: 現在の温度
- H × R: 現在の温度
- ...

## 直近の情報格差
- info_gap の一行

## 参照
- 詳細は canon/active/ep-XX.md
```
