# Repository authority

- 作業開始前に CLAUDE.md を最初から最後まで読む。
- CLAUDE.md、canon、specs、story の既存の権限関係を尊重する。
- CURRENT_MILESTONE が完了済み、矛盾、不明確な場合は、ユーザーが明示した作業だけを許可範囲として扱う。
- ユーザーの明示的な許可なしに次のマイルストーンへ着手しない。
- trpg_core/FUTURE.md に「今は実装しない」と書かれた機能を先行実装しない。

# Git safety

- 編集前に `git branch --show-current` と `git status` を確認する。
- main ブランチ上では編集しない。
- commit、push、merge、rebase、tag、ブランチ切替を勝手に行わない。
- `git reset --hard`、`git restore`、`git clean` を実行しない。
- 既存の未コミット変更を取り消さない。

# Implementation scope

- 依頼に必要な最小限のファイルだけを変更する。
- 関係のない整形、リファクタリング、名前変更を行わない。
- 外部依存を追加する前に確認を求める。
- テストを通すためだけに fixture や期待値を書き換えない。
- 乱数消費順と決定論的な再現性を維持する。
- qa/reports、story、canon、meta、tests/fixtures を必要なく再生成しない。
- 外部 LLM API を明示的な許可なしに使用しない。

# Before editing

編集前に次を報告する。

1. 現在のブランチ
2. git status
3. 変更対象ファイル
4. 実装計画
5. テスト計画
6. 既存フィクスチャへの影響
7. 想定リスク

# After editing

編集後に次を報告する。

1. 変更ファイル一覧
2. 各変更の理由
3. git diff --stat
4. 実行したテスト
5. テスト結果
6. 未解決事項とリスク

# Verification

基本回帰テスト:

```text
python -B -m pytest -p no:cacheprovider tests/test_regression.py tests/test_fixtures.py
```

旧 SDND 判定系を変更した場合は、関連する `--regression` または `--selftest` も実行する。
