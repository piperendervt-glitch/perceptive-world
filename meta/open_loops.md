# open_loops.md — 拡張台帳（回収と好奇心）

書込許可: editor のみ。
TIER: 1（常時参照）。

## 目的

- 敷設した伏線・提示した問い・読者への暗黙の約束を一元管理する。
- **回収の次元**と**好奇心の次元**の両方を管理する（伏線＝ただの謎解きではなく、読者を引っ張る燃料として扱う）。

## スキーマ

| 列名 | 型 | 説明 |
|------|-----|------|
| id | string | 一意ID（例: OL-001） |
| 敷設ep | string | 初出のエピソードID（例: ep-01）。まだ書かれていなければ "-" |
| 内容 | string | 何が open なのか。一行要約 |
| 回収予定ep | string | 回収の目安。未定なら "?" |
| status | open / resolved | 現在の状態 |
| last_touched_ep | string | 最後に触れたエピソード。触れないと風化する |
| suspense_level | 0-3 | 現時点の焦らし度合い。3 は読者が今すぐ知りたい状態 |
| promise_to_reader | bool | 「これは必ず回収する」と読者に思わせたか |

## 運用ルール

- **敷設**: writer/director が仕込んだ伏線は、editor が canon 登録時に台帳へ追加する。
- **触れる**: 触れた話ごとに last_touched_ep を更新する。3話連続で触れていない promise_to_reader=true の項目は Warning。
- **回収**: 回収した話で status=resolved にする。resolved 後も削除しない（履歴として残す）。
- **緩急**: suspense_level は自然増（触れないと下がる／触れると上下）。全項目が 3 の状態は疲弊、全項目が 0 の状態は退屈。

## 初期エントリ

現時点（M1）では本編未着手のため、以下はプレースホルダのみ。M2 以降で editor が実データを追加する。

| id | 敷設ep | 内容 | 回収予定ep | status | last_touched_ep | suspense_level | promise_to_reader |
|----|--------|------|-----------|--------|-----------------|----------------|-------------------|
| OL-000 | - | （初期エントリなし。M2 で追加） | - | - | - | - | - |

## 参照

- 状態の連動 → [[engine_state]]
- 秘密の断片 → [[central_question]]
- ドラマ規律 → [[drama_invariants]]
