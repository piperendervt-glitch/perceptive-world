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

**CL4: playtest-01 を D-clarity で回帰し、正解セット(5フラグ/2通過)と一致するか検証。一致後、Scene1/2 を詩性を保ったまま規律に沿って書き直す。**

### DONE 条件（CL4）

- [ ] D-clarity が正解セットの 5 つを Warning・2 つを通過と判定し、書き直し版が骨を明快にしつつ詩的密度と謎(6,7)を保持する。
- [ ] playtest-01 Scene1/2 を qa_run.py に通し、D-clarity 小片パックを生成→ open_loops 照合で仕分け（正解1〜5=Warning / 6,7=通過）。
- [ ] 不一致は「抽出漏れ / 仕分け誤り」で分類して報告（#5 は欠落型でコード未抽出＝抽出漏れ、判定は一致）。
- [ ] 書き直し版 `story/playtest-01-s{1,2}-rev.md` を作り、1〜5 を一義化（詩性保持）、6,7 は無改変で保護。「起き上がった」は主観と明示（客観だと理破り Blocker）。
- [ ] 書き直し版を QA 再通過（CODE 通過・D-clarity 骨の不明瞭ゼロ）。`story/playtest-01.md` に元と対比で併記。
- [ ] 検証専用。canon/active 未登録。次 Step(C/D) には手を付けない（先回りしない）。
- [ ] git commit 後、`vCL.4` タグが打たれている。

### ハイブリッド QA の役割分担（現行・道A）

- **CODE 領域**（決定論的に判定, Q1）: C-9.3, C-9.6, C-11.1, C-11.3。`qa_deterministic.py`。
- **HYBRID 候補抽出**（コードが小片を抽出, Q2）: C-9.7/C-10, C-11.2, C-9.1/C-9.2/C-9.4/C-12.3。`qa_deterministic.py`。
- **統合ランナー**（CODE→早期FAIL→小片パック出力, Q4）: `qa_run.py`。**外部API不使用**。
- **意味判断**（道A）: 小片パックを **Claude Code セッション内**で読んで下す（C-11.4/C-11.2/C-9.7/C-10/C-9.5）。判定は consistency レポートに統合。
- **API 経路（温存・未使用）**: `qa_llm.py` + `llm_provider.py` + `config/llm.yaml`。将来 API 方針に切り替える場合、`qa_run.emit_semantic_work()` を `call_llm()` に差し替える（Step3 の境界）。

### QA 運用手順（道A・APIキー不要）

`qa_run.py <ep>` を実行すると、まず CODE（算術・構造）を決定論で判定し、Blocker/Major があれば**早期FAIL**して writer に差し戻す（意味判断は起こさない＝トークン節約）。CODE 通過時のみ意味判断用の小片パック `qa/reports/pending-llm-<ep>.md` が出る。**この小片パックを Claude Code セッションが読み**、各項目（C-11.4 意味的重複 / C-11.2 理干渉 / C-9.7・C-10 話者 / C-9.5 変化量 / **D-clarity 明瞭さ**）の重大度を記入欄に判定する（外部API不使用）。判定結果は `qa/reports/consistency-<ep>.md` に統合する（editor 相当の書き込み）。**QA の算術・構造はコード＋早期FAIL、意味判断は Claude Code セッション内で完結する。**

**D-clarity（明瞭さ・I-D8/I-D9）の判定手順（セッション内）**: コードが `extract_ambiguity_candidates` で曖昧さ候補（missing_referent / literal_breaking / supernatural）を機械抽出し、パックに載せる。セッションは各候補を [[engine_state]] の open_loops（登録済みの謎。playtest ではスライスの decision_log の OL-*）と照合し、**登録謎に直接繋がれば 通過、繋がらなければ Warning**（指示対象不明・主観/客観不明・字義破壊の比喩）と仕分ける。超常候補は `meta.has_subjective_marker` と invariants 適合も見る（I-D9）。**詩的密度そのものは減点しない**——見るのは曖昧さの「配分」だけ。判定は consistency（もしくは drama）レポートに統合する。

### 完了済みマイルストーン

- **M1**: リポジトリ骨格とコア仕様の作成（tag `v0.1-scaffold`）。
- **A1**: canon/status.yaml のシード（tag `vA.1`）。
- **A2**: writer delta → 整合性QA 数値検査 → editor 適用 の1周（tag `vA.2`）。
- **A3**: 数値の可視性規律の強制（tag `vA.3`）。
- **B1**: 決定点の選択肢構造出力と C-11 検査（tag `vB.1`）。
- **Q1**: qa_deterministic.py に CODE 項目（C-9.3/C-9.6/C-11.1/C-11.3）を実装（tag `vQ.1`）。
- **Q2**: qa_deterministic.py に HYBRID 候補抽出を実装（抽出のみ・判定なし・LLM 不使用）（tag `vQ.2`）。
- **Q3**: qa_llm.py + llm_provider.py + config/llm.yaml。小片入力の LLM 判断関数群（API 経路。温存・未使用）（tag `vQ.3`）。
- **Q4（道A）**: qa_run.py（CODE→早期FAIL→小片パック出力・外部API不使用）（tag `vQ.4`）。
- **playtest-01**: 通し検証スライス（D1=B, 両シーン PASS・canon 未登録・タグなし）。
- **CL1**: drama_invariants.md に I-D8 / I-D9（明瞭さの規律）を追加（tag `vCL.1`）。
- **CL2**: writer.md に I-D8/I-D9 に沿う執筆指針（明瞭さの規律）を追加（tag `vCL.2`）。
- **CL3**: drama_checklist.md に D-clarity、qa_deterministic.py に `extract_ambiguity_candidates`（抽出のみ・判定なし）（tag `vCL.3`）。
- **CL4**: playtest-01 を D-clarity で回帰（正解 7/7 一致）し、Scene1/2 を詩性保持で書き直し（`*-rev.md`）（tag `vCL.4`）。

### 次のマイルストーン（指示があるまで着手しない）

- **Step C/D（editor のローカル化 等）**: 指示があるまで着手しない。
- **B2 以降**: 選択の記録と分岐実行。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
