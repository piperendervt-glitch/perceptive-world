# engine_state.md — ドラマ状態

書込許可: director のみ（次話の狙い設定時）／ editor（canon 登録後の状態更新）。
TIER: 1（常時参照）。

## 現在の状態（初期）

```
tension: 2
last_turn_direction: "-"
open_questions: []
unpaid_promises: []
info_gap: "読者と転生者はステータスが見えるが、現地人は見えない"
mode_hint: ""
```

## 各フィールドの意味

- **tension** (0-3): 現時点の緊張レベル。次話の緩急設計に使う。0=弛緩、1=平静、2=緊張、3=切迫。
- **last_turn_direction**: 直近の話でのターン方向（"+"/"-"/"±"）。単調化を避けるために参照する。初期値 "-" は「まだ話がないため未定」の意。
- **open_questions**: 未回収の中心的な問い。[[open_loops]] のうち suspense_level が高いものと連動。
- **unpaid_promises**: 読者に対して「これは回収する」と暗黙に約束した事象。promise_to_reader=true の open_loops と連動。
- **info_gap**: 現在アクティブな情報格差。初期は転生者と現地人のステータス可視性の差。
- **mode_hint**: 次話に対する director の一言指示（例: "静けさで恐怖", "同盟の破れ目"）。初期は空。

## 更新規則

- director は各話の執筆開始前に mode_hint を更新する。
- editor は canon 登録後に tension, last_turn_direction, open_questions, unpaid_promises を更新する。
- writer と qa はこのファイルを**読むのみ**。書き換えない。

## 参照

- 拡張台帳（open_loops）→ [[open_loops]]
- ドラマ規律 → [[drama_invariants]]
