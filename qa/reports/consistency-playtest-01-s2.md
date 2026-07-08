# consistency-playtest-01-s2 — 整合性QA レポート

生成: qa_run.py（Q4 / 道A・外部API不使用）

## CODE 判定（決定論・qa_deterministic）

| 項目 | 判定 | 理由 |
|---|---|---|
| C-9.3 | 通過 | All applied deltas keep hp.cur/mp.cur within [0, max]. |
| C-9.6 | 通過 | All delta.char present in status.characters. |
| C-11.1 | 通過 | no decision block. |
| C-11.3 | 通過 | no decision block. |

## 早期FAIL: なし

- CODE 段 通過。意味判断は **pending**。
- 小片パック: `pending-llm-playtest-01-s2.md`
- 想定 LLM 判断数: **2**（Claude Code セッション内で判定）

## 意味判断（Claude Code セッション内・道A / 外部API不使用）

`pending-llm-playtest-01-s2.md` の小片を読んで判定（editor 相当の統合）:

| 項目 | 小片 | 判定 | 理由 |
|---|---|---|---|
| C-9.7/C-10 | `（残り MP 1。あと一度きり）` | 通過 | H の括弧内内語。女が見たのは「青い光」（質的）で数値ではない（I-4 保持）|
| C-9.5 | mp.cur −1 ← 「いちばん小さな灯火」 | 通過 | 極小の灯火に MP−1 は事象規模に見合う（不相応な急変ではない）|

意味判断: Blocker 0 / Major 0 / Warning 0。

## 総合判定: **PASS**（CODE 通過 + 意味判断すべて通過）

- 数値ループ: canon H.mp.cur=2 に delta −1 適用後 = 1（[0,10] 内・クリップなし）。
- ドラマ軸メモ（参考）: ターン=「読めば分かる」→「問いが逆に覗き返す／女に露見」（I-D1）。得た＝失った=断片の一片と MP を得て、女の無垢な距離と隠蔽を失う（I-D5）。中心の問いは開いたまま深化（I-D2）。露見は代償ありで情報格差が動いた（I-D7）。
