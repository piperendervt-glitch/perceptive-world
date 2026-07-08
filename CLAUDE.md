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

**Q2: qa_deterministic.py にHYBRIDの候補抽出（C-9.7/C-10 数値露出, C-11.2 理干渉フラグ, C-9.1/C-9.2/C-9.4/C-12.3 のコード側）を実装。抽出のみ、判定はしない。**

### DONE 条件（Q2）

- [ ] 各 HYBRID 項目について「LLM に問うべき小片」が構造化抽出される（`{item, candidates:[{snippet, meta}], needs_llm: true}`）。
- [ ] `extract_numeric_mentions` が HP/MP/レベル/具体数値の言及箇所を「該当文±前後1文」で切り出す（本文全体は渡さない）。
- [ ] `flag_ri_interference` が「requires 空 かつ label/intended_shift が理に言及」する option をフラグ。
- [ ] `extract_cause_pairs` が各 delta の cause と本文事象候補を対にする。
- [ ] B1 の**違反版**（story/ep-00-b1test-violation.md）で理干渉フラグが「対価なしの理破り」option（D）に立つ。
- [ ] A2/A3 検証話で `extract_numeric_mentions` が数値言及を漏れなく抽出する。
- [ ] 抽出のみ。判定（PASS/Major 等）はしない。LLM は呼ばない。
- [ ] git commit 後、`vQ.2` タグが打たれている。

### ハイブリッド QA の役割分担（Q2 時点）

- **CODE 領域**（決定論的に判定, Q1）: C-9.3, C-9.6, C-11.1, C-11.3。
- **HYBRID 候補抽出**（コードが小片を抽出→後段で LLM が意味だけ判断, Q2）: C-9.7/C-10（数値露出）, C-11.2（理干渉）, C-9.1/C-9.2/C-9.4/C-12.3（cause↔事象）。**Q2 は抽出まで。判定は Q3 以降で LLM に渡す。**
- **LLM 領域**（Q3 以降で接続）: 抽出された candidates に対する意味判断（invariants 適合, 飾り検出, 可視性帰属など）。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。
- **A2**: writer delta → 整合性QA 数値検査 → editor 適用 の1周（tag `vA.2`）。
- **A3**: 数値の可視性規律の強制（tag `vA.3`）。
- **B1**: 決定点の選択肢構造出力と C-11 検査（tag `vB.1`）。
- **Q1**: qa_deterministic.py に CODE 項目（C-9.3/C-9.6/C-11.1/C-11.3）を実装（tag `vQ.1`）。

### 次のマイルストーン（指示があるまで着手しない）

- **Q3 以降**: 抽出された candidates を実際に LLM に渡し、意味判断を統合（ハイブリッド QA 化）。
- **B2 以降**: 選択の記録と分岐実行。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
