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

**A3: 数値は転生者の知覚を通してのみ言及される、という可視性規律を writer と QA に強制する。**

### DONE 条件（A3）

- [ ] writer 定義に、数値は転生者の知覚を通してのみ言及する旨のルールが明記されている。現地人視点／地の文では質的表現に留める。
- [ ] consistency_checklist.md に可視性検査（地の文の数値露出、非転生者視点／台詞の数値露出、帰属の明示）が追加されている。
- [ ] drama_checklist.md に、情報格差が装置として機能しているかを問う項目が追加されている（形骸化は Warning）。
- [ ] 検証用の薄い1話を1つだけ通し、現地人1人が登場し、地の文と現地人視点が数値に触れないことを consistency QA が確認する。
- [ ] 意図的な違反版に対して consistency QA が I-4 違反 (Major) を検出することを、QA レポートに記録している。
- [ ] git commit 後、`vA.3` タグが打たれている。
- 注: A3 検証話でもドラマQA は必須にしない（Step A の検証話に共通する例外）。本番エピソード（M2 以降）では引き続き両方 PASS が必要。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。
- **A2**: writer delta → 整合性QA 数値検査 → editor 適用 の1周（tag `vA.2`）。

### 次のマイルストーン（指示があるまで着手しない）

- **Step B**: 選択の挿入。**指示があるまで着手しない**。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
