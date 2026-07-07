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

**Q1: qa_deterministic.py に CODE 項目（C-9.3 / C-9.6 / C-11.1 / C-11.3）を実装。LLM は呼ばない。**

### DONE 条件（Q1）

- [ ] `qa_deterministic.py` に 4 つの CODE 項目が実装され、LLM を一切呼ばずに JSON/表形式で判定を返す。
- [ ] 同じ入力に対して常に同じ結果（temperature も乱数もない）。
- [ ] decision ブロックと status_delta のパーサが writer 出力の YAML を読める。壊れた入力は明示エラー。
- [ ] B1 の**違反版**（story/ep-00-b1test-violation.md）で `C-11.1=Major`（MP 不足）を検出する。
- [ ] B1 の**正しい版**（story/ep-00-b1test.md）で CODE 4 項目すべて **通過**。
- [ ] git commit 後、`vQ.1` タグが打たれている。

### ハイブリッド QA の役割分担（Q1 時点）

- **CODE 領域**（qa_deterministic.py で決定論的に判定）: C-9.3, C-9.6, C-11.1, C-11.3。
- **LLM 領域**（Q2 以降で扱う。Q1 時点では Claude が担当）: C-11.2（invariants 適合）, C-11.4（飾り検出）, C-10（可視性）, その他意味理解が要る項目。
- LLM 領域のローカル化は Phase 0 で不合格。Blocker/Major を見逃すため、Claude に残す。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。
- **A2**: writer delta → 整合性QA 数値検査 → editor 適用 の1周（tag `vA.2`）。
- **A3**: 数値の可視性規律の強制（tag `vA.3`）。
- **B1**: 決定点の選択肢構造出力と C-11 検査（tag `vB.1`）。

### 次のマイルストーン（指示があるまで着手しない）

- **Q2 以降**: LLM を呼ぶ意味理解系 QA（C-11.2 など）の統合、ハイブリッド QA 化。
- **B2 以降**: 選択の記録と分岐実行。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
