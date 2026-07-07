# sdnd-ordia

Spec-Driven Novel Development v2（**SDND v2**）を用いた、異世界転生ファンタジー『Ordia』のリポジトリ。

## SDND v2 とは

小説執筆を、仕様と検査によって駆動する枠組み。二つの独立した「軸」を持つ:

- **整合性軸（Consistency）**: 世界の不変ルール（specs/core/invariants.md）に照らして違反を検査する。
- **ドラマ軸（Drama）**: 面白さの規律（specs/core/drama_invariants.md）に照らしてターン・緊張・問い・代償を検査する。

**両方の QA を通ってはじめて canon（正史）に登録される**。整合性だけでは退屈、ドラマだけでは破綻する — その両立を仕組みで保証する。

## Ordia の世界

- ジャンル: 異世界転生ファンタジー。魔法は一般的に使え、血統が強さを決める。
- **理（ことわり）**: 世界の根本法則。何者もこれから外れることはできない。
- **ステータス**: 転生者にしか見えない数値。これは便利機能ではなく「知ってしまう格差＝呪い」として扱う。
- 中心の問い: 「理とは何か。なぜ何者もそこから外れられないのか。」
- 中核テーマ: **秘密に近づく＝何かを失う**。真理を得ることが、この世界に居る資格や大切なものを失うことを意味する。

詳細は specs/core/ を参照。

## ディレクトリ構成

```
sdnd-ordia/
  CLAUDE.md            # ガードレール（AI エージェント向け）
  README.md            # 本書
  specs/
    core/              # 変えない前提（TIER1 常時参照）
    reference/         # 詳細ロア（TIER3 随時）
  canon/
    quick_ref.md       # 最新要約（TIER1）
    active/            # 直近5話（TIER2）
    archive/           # 古い話
  meta/
    engine_state.md    # ドラマ状態（緊張・ターン・約束）
    open_loops.md      # 拡張台帳（回収＋好奇心）
  qa/
    consistency_checklist.md
    drama_checklist.md
    reports/           # 各話の検査結果
  .claude/agents/
    writer.md director.md editor.md qa.md
  story/               # 本編（M1 では空）
```

## エージェントと権限

| エージェント | 役割 | 書込許可 |
|--------------|------|---------|
| director | 次話の劇的狙いを指示 | meta/engine_state.md のみ |
| writer | 本編を執筆 | story/ のみ |
| qa | 整合性＋ドラマの検査 | qa/reports/ のみ |
| editor | canon 登録・状態更新 | specs/, canon/, meta/ |

いずれも許可領域外を書き換えない。

## ワークフロー

```
director（mode_hint）→ writer（執筆）→ qa（整合性＋ドラマ、両方）
  → 両方 PASS → editor（canon 登録 & meta 更新）→ git commit
```

## 現状マイルストーン

**M1: リポジトリ骨格とコア仕様の作成。本編は書かない。**

M2 以降で第1話の執筆に入る。詳細は CLAUDE.md を参照。
