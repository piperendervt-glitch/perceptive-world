# CLAUDE.md — sdnd-ordia ガードレール

## PRIME DIRECTIVE

- **CURRENT_MILESTONE だけを実装する。先を作らない。**
- **本編（story/）は書かない**（M1 では絶対に書かない）。
- 迷ったら小さい方を選ぶ。指定範囲を作り終えたら停止して次の指示を待つ。

## 不変条件（システム側）

1. **canon が真実源**。specs/core と canon は世界の事実として扱う。矛盾したときは canon > specs > story の優先順位で判断する（specs の変更は editor のみ）。
2. **エージェント権限の分離**（詳細は .claude/agents/*.md）:
   - writer: story/ のみ書込可
   - qa: qa/reports/ のみ書込可
   - editor: specs/, canon/, meta/ 書込可
   - director: meta/engine_state.md のみ書込可
   - **各エージェントは自分の許可領域外を書き換えない**。
3. **canon 登録には整合性QA と ドラマQA の両方の PASS が必要**。片方だけでは登録不可。
4. TIER 方式で context を有界化する:
   - TIER1（常時）: specs/core/*, canon/quick_ref.md, meta/*, qa/*_checklist.md
   - TIER2（直近5話）: canon/active/*
   - TIER3（随時）: specs/reference/*, canon/archive/*

## ワークフロー

```
director（mode_hint 更新）
    ↓
writer（story/ep-XX.md を執筆）
    ↓
qa（consistency & drama の両方を検査、qa/reports/ に出力）
    ↓
両方 PASS?
    ├─ No → writer に差し戻し
    └─ Yes → editor（canon 登録、meta 更新）
                ↓
              git commit
```

## CURRENT_MILESTONE

**B1: 決定点で 2〜4 個の選択肢を構造出力する。各選択肢は status.yaml と invariants で実行可能性を検証。分岐はしない。**

### DONE 条件（B1）

- [ ] writer 定義に decision ブロック（id / prompt / options / requires / intended_shift）の出力仕様と、選択肢に関する規律が明記されている。
- [ ] consistency_checklist.md に C-11（選択肢検査）が追加され、requires 充足性・invariants 適合・個数 2〜4・飾り選択検出・可視性適用の各項目を検査できる。
- [ ] 検証用の薄い1話を1つだけ通し、決定点を 1 個置いて decision ブロックが出力されている（分岐は行わない）。
- [ ] 意図的な違反版（実行不能な選択肢・飾りの重複選択肢・invariants 違反の選択肢）を投入し、C-11 が Major / Warning / Blocker で検出することを QA レポートに記録している。
- [ ] git commit 後、`vB.1` タグが打たれている。
- 注: B1 検証話でもドラマQA は必須にしない（Step A の検証話に準じた例外）。本番エピソード（M2 以降）では引き続き両方 PASS が必要。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。
- **A2**: writer delta → 整合性QA 数値検査 → editor 適用 の1周（tag `vA.2`）。
- **A3**: 数値の可視性規律の強制（tag `vA.3`）。

### 次のマイルストーン（指示があるまで着手しない）

- **B2 以降**: 選択の記録と分岐実行（未着手）。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
