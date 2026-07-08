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

**D3（出目モード＋代償描写＋構造化ログ）: 出目表示モード(reveal_dice, デフォルトON)を実装。writer が tier を物語として描写(success_with_cost=I-D5 の代償を織る)。判定を構造化ログに記録。**

### DONE 条件（D3・出目モード＋代償描写＋構造化ログ）

- [x] 出目モードで表示/非表示が切替でき（既定=表示）、writer が tier に応じた描写（特に success_with_cost で代償）を書き、判定が構造化ログに残る。
- [x] `config/play.yaml` の `reveal_dice`（既定 true）。true=dice/total/target/tier を提示、false=tier の帰結だけ提示し出目は内部ログのみ。
- [x] `present_result(result, reveal_dice=)` で提示が切り替わる。writer の散文は reveal_dice に依存しない。
- [x] writer.md に tier→帰結の描き方（full_success/success_with_cost=I-D5/failure/critical/fumble）。明瞭さ規律 I-D8/I-D9 準拠。
- [x] `meta/play_log.yaml` に構造化ログ（decision_log の拡張）: turn/decision_id/chosen/action_type/dice/total/target/tier/modifier/cost_applied/consequence/status_delta/scene_ref/seed。**出目非表示でもログには出目を残す**。
- [x] D1 の器 `make_log_entry` を実運用に接続（resolve を verbatim 内包）。動画機能そのものは作らない（素材化まで）。
- [x] 回帰: reveal 両モードで提示が変わりログは両方完全、success_with_cost で代償描写＋`cost_applied`(mp/id5_fired) 記録。
- [x] 回帰（D4）は先回りしない。本編は書かない。
- [x] git commit 後、`vD.3` タグが打たれている。

### 判定エンジン（resolve.py・D1）

- **3 段階＋ゾロ目**: `critical`(6-6・無条件) / `full_success`(total≥target+MARGIN_BAND) / `success_with_cost`(target≤total<target+MARGIN_BAND・**I-D5 発火**) / `failure`(total<target) / `fumble`(1-1・無条件)。
- **MARGIN_BAND=3**（代償帯の幅・調整可能）。ゾロ目は目標比較より優先（無条件）。
- **乱数はコード独占**: `resolve(modifier, target, seed=None)`。seed 未指定でも再現可能なシードを引いて結果に記録。`classify()` は純関数（dice+total+target のみ）で境界テスト可能。
- D2 では `modifier` を status から算出、`target` は Adjudicator が決める（D1 では引数）。

### ステータス連動（status_resolve.py・D2）

- **D1 は無改変**。`status_resolve.py` が resolve() の手前に「供給層」を足す（`from resolve import resolve, make_log_entry`）。
- **行動種別→使用能力（Ordia 自前の対応表）**: `magic→mag`（魔法的・血統相関 I-3 の効く軸）/ `force→str`（力技）/ `endure→vit`（耐久）。魔法的行動＝`MAGIC_ACTIONS`。
- **modifier 算出**: `modifier_from_status(action_type, char, status) = attribute - ABILITY_PIVOT`。`ABILITY_PIVOT=8`（status.yaml の「血統補正なしの一般人相当」＝±0）。純関数。
- **魔法は MP 消費（I-2）**: `MAGIC_MP_COST=2`（可変・引数で上書き）。`resolve_action()` は魔法時に MP を引き、`status_delta:[{char, change:{mp.cur:-cost}, cause}]`（Step A/B の delta 機構を再利用、適用は editor）を添える。
- **MP 不足は試行不可（C-11.1 整合）**: `cur_mp < cost` なら乱数を振らず `attempted:false, blocked:insufficient_mp` を返す。`magic_requires()` が同形式の `requires:{mp:cost}` を吐き、決定点で C-11.1 に載せられる。
- **I-3 が数値として効く**: 血統のない H は mag=8 → 魔法 modifier=0。血統持ちは mag 上振れ→正の modifier。同 seed で mag が高いほど tier は成功寄り（回帰で単調性を確認）。
- **resolve は verbatim 内包**: `resolve_action(...)["resolve"]` は D1 の返り値そのまま。`make_log_entry` にそのまま載る（D3 で拡張）。

### 出目モード・代償描写・構造化ログ（play_log.py・D3）

- **出目表示モード**: `config/play.yaml` の `reveal_dice`（既定 **true**）。`load_reveal_dice()` が読む。`present_result(result, reveal_dice=)` が提示を切替 —— true=dice/total/target/tier を見せる、false=`TIER_OUTCOME` の帰結（物語の形）だけ見せ出目は伏せる。**どちらでも play_log には出目を残す**（内部真実の保持）。
- **tier の帰結描写（writer.md）**: `critical`=好転＋一歩 / `full_success`=叶う代償なし / `success_with_cost`=**I-D5（得た＝失った）を必ず織る** / `failure`=状況悪化（Director 燃料）/ `fumble`=特別な悪化。数値は地の文に再掲しない（C-10）。曖昧さは登録謎の周りだけ（I-D8/I-D9）。writer の散文は reveal_dice に依存しない。
- **構造化ログ（動画化の素材）**: `meta/play_log.yaml`（decision_log の拡張, editor 書込, TIER3）。`make_play_log_entry()` が `{turn, decision_id, chosen, char, action_type, dice, roll_total, modifier, total, target, tier, cost_applied{mp,id5_fired}, consequence, status_delta, scene_ref, reveal_dice, seed, resolve}` を吐く。`append_play_log()` で追記（ヘッダ保存・エイリアス無効）。**動画機能そのものは作らない**（素材化まで）。
- **make_log_entry を実運用に接続**: `make_play_log_entry` は D1 の器 `make_log_entry` を通して resolve を verbatim 内包（seed 込み＝動画再生成が可能）。
- **cost_applied**: `mp`=I-2 の機構コスト（status_delta の mp.cur 消費量）、`id5_fired`=I-D5 発火（`tier==success_with_cost`）。弾かれた判定（attempted=false）もログに残す（dice/resolve は null, cost.mp=0）。

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
- **D1（判定エンジン）**: resolve.py に 2D6＋修正→3段階（＋ゾロ目 critical/fumble）の判定エンジン。乱数はコード独占・seed 再現可能（tag `vD.1`）。
- **D2（ステータス連動）**: status_resolve.py に 行動種別→使用能力の対応、`modifier_from_status`（attr-PIVOT）、魔法判定の MP 消費（I-2）と MP 不足の弾き（C-11.1 整合）。D1 は無改変で供給側を追加。Hの低い mag が魔法判定の不利として効く（I-3）（tag `vD.2`）。
- **D3（出目モード＋代償描写＋構造化ログ）**: play_log.py に 出目表示モード（`config/play.yaml` reveal_dice, 既定 true）、`present_result`、tier 帰結の writer 指針（writer.md, success_with_cost=I-D5）、構造化ログ `meta/play_log.yaml`（`make_play_log_entry`/`append_play_log`, make_log_entry を実運用接続）。動画機能は未実装（素材化まで）（tag `vD.3`）。

### 次のマイルストーン（指示があるまで着手しない）

- **D4**: 判定エンジンの回帰・通し検証（指示があるまで着手しない）。
- **Step C（editor のローカル化 等）**: 指示があるまで着手しない。
- **B2 以降**: 選択の記録と分岐実行。
- **M2**: 第1話（ep-01）の本番執筆。director → writer → qa × 2 → editor → commit の一巡を通す。

## 禁止事項

- 指示された骨格範囲を超えて機能・話・キャラを追加する。
- specs/core/invariants.md, drama_invariants.md の意味を変える。
- 本編（story/*）を先回りして書く。
- axios のバージョン揺れ（^, ~ を使わない）。本プロジェクトは Node/npm を使わない予定だが、将来使う際も遵守。
