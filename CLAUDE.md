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

**Q3: LLM 判断項目を、Q2 の抽出小片を入力に、最小プロンプトで Claude に問う関数群を実装。プロバイダ抽象経由・temperature=0・JSON強制・壊れたら1回再要求。**

### DONE 条件（Q3）

- [ ] 各 LLM 項目が小片入力で判定を返す（`qa_llm.py`）: C-11.4（意味的重複）, C-11.2（理干渉）, C-9.7/C-10（話者）, C-12.1/C-12.2（選択反映）, C-9.5（変化量妥当性）。
- [ ] 入力は**小片のみ**（本文全体・チェックリスト全文は渡さない）。C-11.4 は id+intended_shift だけ、C-11.2 はフラグ済み option の label/shift + 理の定義、C-9.7/C-10 は該当文±前後1文。
- [ ] temperature=0（llm.yaml の qa ロール）、JSON 強制（output_config.format）、壊れたら 1 回だけ再要求。
- [ ] モデルは `config/llm.yaml` の qa ロール（軽量 Claude = Haiku 4.5）から読む。プロバイダ抽象（`llm_provider.py`）経由。
- [ ] B1 違反版で、飾り重複を C-11.4=**Warning**、対価なし理破りを C-11.2=**Blocker** で検出。
- [ ] 現地人の数値露出 NG 例を C-9.7/C-10=**Major** で検出。B1 正しい版で C-11.4 は誤検出しない。
- [ ] git commit 後、`vQ.3` タグが打たれている。

### ハイブリッド QA の役割分担（Q3 時点）

- **CODE 領域**（決定論的に判定, Q1）: C-9.3, C-9.6, C-11.1, C-11.3。
- **HYBRID 候補抽出**（コードが小片を抽出, Q2）: C-9.7/C-10, C-11.2, C-9.1/C-9.2/C-9.4/C-12.3。`qa_deterministic.py`。
- **LLM 判断**（抽出小片を最小プロンプトで軽量 Claude に問う, Q3）: C-11.4, C-11.2, C-9.7/C-10, C-12.1/C-12.2, C-9.5。`qa_llm.py` + `llm_provider.py` + `config/llm.yaml`。
- **統合パイプライン**（Q4 以降）: CODE 判定 + 抽出 + LLM 判定を 1 本のレポートにまとめ、director→writer→qa→editor の一巡に載せる。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。
- **A2**: writer delta → 整合性QA 数値検査 → editor 適用 の1周（tag `vA.2`）。
- **A3**: 数値の可視性規律の強制（tag `vA.3`）。
- **B1**: 決定点の選択肢構造出力と C-11 検査（tag `vB.1`）。
- **Q1**: qa_deterministic.py に CODE 項目（C-9.3/C-9.6/C-11.1/C-11.3）を実装（tag `vQ.1`）。
- **Q2**: qa_deterministic.py に HYBRID 候補抽出を実装（抽出のみ・判定なし・LLM 不使用）（tag `vQ.2`）。

### 次のマイルストーン（指示があるまで着手しない）

- **Q4 以降**: CODE 判定 + 抽出 + LLM 判定を統合したハイブリッド QA パイプライン化。
- **B2 以降**: 選択の記録と分岐実行。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
