# Repository authority

- 作業開始前に `CLAUDE.md` を最初から最後まで読む。
- `CLAUDE.md`、canon、specs、story の既存の権限関係を尊重する。
- `CURRENT_MILESTONE` が完了済み、矛盾、不明確な場合は、ユーザーが明示した作業だけを許可範囲として扱う。
- ユーザーの明示的な許可なしに次のマイルストーンへ着手しない。
- `trpg_core/FUTURE.md` に「今は実装しない」と書かれた機能を先行実装しない。

# Git safety

- 編集前に現在の branch、HEAD、`git status`、staged 差分を確認する。
- main ブランチ上では編集しない。
- 想定外のユーザー差分を変更、破棄、上書きしない。
- `git reset`、`git restore`、`git clean`、`git stash` でユーザー差分を消さない。
- commit、push、pull、fetch、merge、rebase、cherry-pick、tag、branch 切替・作成は、ユーザーが明示的に許可した場合だけ行う。
- `git add .` と `git add -A` は使用しない。stage 対象はファイル名を明示する。
- force push を行わない。
- protected fixture を変更、stage、commitしない。

# Implementation scope

- 依頼に必要な最小限のファイルだけを変更する。
- 関係のない整形、リファクタリング、名前変更を行わない。
- 外部依存を追加する前に確認を求める。
- テストを通すためだけに fixture や期待値を書き換えない。
- qa/reports、story、canon、meta、tests/fixtures を必要なく再生成しない。
- 外部 LLM API を明示的な許可なしに使用しない。
- import 時に I/O、RNG、environment mutation を行わない。

# Determinism and engine boundaries

- wall-clock、FPS、非seed RNGへ依存しない。
- 乱数消費順と決定論的な再現性を維持する。
- live play と replay は同じ canonical engine dispatcher を使用する。
- replay 専用の直接 state mutation を作らない。
- liveで受理できるactionはrecord/replay可能、liveで変更できるstateはsave/load可能にする。
- schema変更はlegacy migrationとatomic load validationを同時に実装し、中途半端なversion状態を残さない。
- invalid actionはatomicに拒否し、state、RNG、log、recordを部分変更しない。
- render／presentationはauthoritative stateを変更しない。

# LOD and information boundaries

- engineがattention、cap、focusなどのauthoritative stateを所有する。
- current LODは保存せず、authoritative stateから導出する。
- focus設定だけでattentionを増やさない。
- presentation、TUI、save、record、traceへhidden factsやpresentation labelを複製しない。
- TUIはpresentation snapshotだけを参照し、hidden factsを取得しない。
- canonical actionではexact `WorldObjectId`を使用し、partial IDやlabel fallbackを行わない。
- domain層からpresentation／TUIへ依存せず、import cycleを作らない。

# Before editing

編集前に簡潔に次を報告する。

1. 現在のbranchとHEAD
2. git statusとstaged差分
3. 変更対象ファイル
4. 実装計画
5. テスト計画
6. 既存fixtureへの影響
7. 想定リスク

# Testing workflow

- 編集中は変更対象に最も近いfocused testだけを実行する。
- 成功時は `-q` を使い、全test名やdot列を完了報告へ転記しない。
- Gate完了時は、そのGateで新たに影響を受けたtest群だけを実行する。
- 前Gateから関連ファイルが変わっていない場合、同じ成功testを理由なく繰り返さない。
- failure後はfull suiteではなく、最初のfailing testを `--tb=short` で再実行する。必要な場合だけ `-vv` やfull tracebackを使う。
- replay、save migration、fixtureなど高リスク境界のfocused testは省略しない。
- full suiteは最終統合時に原則1回実行する。決定論確認など明示的に連続実行する意味があるものだけ繰り返す。
- Windowsでpytestの既定temp directoryが使えない場合、repository内の明示的な一時directoryを`--basetemp`に使い、検証後に安全確認して削除する。

基本回帰テスト:

```text
python -B -m pytest -q -p no:cacheprovider tests/test_regression.py tests/test_fixtures.py
```

最終統合:

```text
python -B -m pytest -q -p no:cacheprovider
```

旧SDND判定系を変更した場合は、関連する`--regression`または`--selftest`も実行する。

# Test reporting

成功時は次だけを要約する。

- passed件数
- elapsed time
- warning／skipの有無
- exit code

失敗時は次を報告する。

- failing test名
- 最初の有用なtraceback
- 原因
- 修正内容

# Gate workflow

- Gate開始時に、そのGateで変更するファイルを確定する。
- Gate終了時は、そのファイルへ直接関係するtestだけを実行する。
- 次Gateで同じファイルを再変更した場合だけ、関連testを再実行する。
- validation削減を目的に安全性を落とさない。削減対象は重複実行と冗長な成功出力だけにする。

# After editing

編集後に簡潔に次を報告する。

1. 変更ファイル一覧と理由
2. `git diff --stat`
3. 実行したtestと結果
4. staged状態と`git status`
5. protected fixtureへの影響
6. 未解決事項とリスク

通常の完了報告は最大20〜25行程度を目安とし、既知の成功項目を長い監査表として繰り返さない。推奨形式:

```text
Phase:
Status:

Changed:
- production:
- tests:
- fixtures:

Contracts:
- schema:
- canonical actions:
- atomicity:
- backward compatibility:

Verification:
- focused:
- full suite:
- replay:
- CLI/import:
- diff check:

Git:
- branch / HEAD:
- staged:
- status:
- protected fixture hash:

Risks:
- ...

Next:
- commit可能 / 未可能
```

# Prompt hygiene

- `AGENTS.md`にある恒久ルールをPhase promptへ毎回全文転載しない。
- Phase promptには、そのPhase固有の目的、変更範囲、acceptance criteriaだけを書く。
- protected fixture名など作業上必須の識別情報だけはPhase promptへ明記してよい。
- baseline hash、期待test件数など将来古くなる現在値を恒久ルールへ書かない。
- 実装監査とcommit監査を別promptへ分け、変更がなければ同じ監査を繰り返さない。

# Usage reporting

- model、tokens、credits、context使用量、compaction回数などは、実行環境が実際に表示・提供した値だけを報告する。
- 推測値や、totalから逆算した内訳を実測値として扱わない。
- 過去のPhaseと現在sessionのusageを混同しない。
- 取得できない項目は「この実行環境では取得不可」と明記する。
- credential探索、外部accountへのlogin、browser automation、API key探索をusage確認目的で行わない。
