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

**A2: writer の status_delta 出力 → 整合性QA の数値検査 → editor の適用＆書き戻し、を薄い1話で通す。**

### DONE 条件（A2）

- [ ] writer 定義に status_delta の出力仕様が明記されている。
- [ ] consistency_checklist.md に数値検査項目（cause の実在、I-2 の MP 消費強制、[0,max] 範囲、I-1/I-6 尊重、変化量の妥当性）が追加されている。
- [ ] editor 定義に、delta を [0,max] にクリップして status.yaml に適用する手順と、quick_ref.md 更新が明記されている。
- [ ] 検証用の薄い1話を1つだけ通し、数値が変化した結果が canon/status.yaml と quick_ref.md に反映されている。
- [ ] 検証話の整合性QAは違反ゼロ（Blocker/Major なし）。
- [ ] git commit 後、`vA.2` タグが打たれている。
- 注: A2 の検証話ではドラマQA は必須にしない（Step A は数値ループ検証が主眼）。本番エピソード（M2 以降）では引き続き両方 PASS が必要。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。

### 次のマイルストーン（指示があるまで着手しない）

- **A3 以降**: 未定（数値ループの拡張・可視化・ダイス等）。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
