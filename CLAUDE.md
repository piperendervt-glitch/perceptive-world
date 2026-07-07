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

**M1: リポジトリ骨格とコア仕様の作成。本編は書かない。**

### DONE 条件（M1）

- [ ] 指定ディレクトリ構造が存在する（specs/core, specs/reference, canon/active, canon/archive, meta, qa/reports, .claude/agents, story）。
- [ ] specs/core/{world, invariants, drama_invariants, characters, conflict_web, central_question}.md が存在し内容がある。
- [ ] meta/{engine_state, open_loops}.md, qa/{consistency_checklist, drama_checklist}.md が存在する。
- [ ] .claude/agents/{writer, qa, editor, director}.md に役割と書込許可が明記されている。
- [ ] invariants と drama_invariants と conflict_web と central_question が互いに矛盾しない。
- [ ] story/ は空。
- [ ] 初回コミット後、`v0.1-scaffold` タグが打たれている。

### 次のマイルストーン（M2、指示があるまで着手しない）

- 第1話（ep-01）の執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
