# consistency-playtest-01-s1 — 整合性QA レポート

生成: qa_run.py（Q4 / 道A・外部API不使用）

## CODE 判定（決定論・qa_deterministic）

| 項目 | 判定 | 理由 |
|---|---|---|
| C-9.3 | 通過 | status_delta is empty; nothing to apply. |
| C-9.6 | 通過 | status_delta is empty. |
| C-11.1 | 通過 | All option.requires satisfiable against canon. |
| C-11.3 | 通過 | option count=3 in [2, 4]. |

## 早期FAIL: なし

- CODE 段 通過。意味判断は **pending**。
- 小片パック: `pending-llm-playtest-01-s1.md`
- 想定 LLM 判断数: **4**（Claude Code セッション内で判定）

## 意味判断（Claude Code セッション内・道A / 外部API不使用）

`pending-llm-playtest-01-s1.md` の小片を読んで判定（editor 相当の統合）:

| 項目 | 小片 | 判定 | 理由 |
|---|---|---|---|
| C-11.4 | A/B/C の intended_shift | 通過 | 隠蔽維持 / 魔力・露見の喪失 / 関係変質 と、動く価値軸も帰結も相異なる（飾りではない） |
| C-11.2 | option A（理へ繋がる糸を手放す） | 通過 | 「手を引く」選択で理を破る・歪める行為ではない。コードは「理」語で機械フラグ→意味判断で非干渉と確定 |
| C-9.7/C-10 | 候補1 `（残り MP 2…）` | 通過 | H の括弧内内語。転生者の知覚で、女には示していない（I-4 保持） |
| C-9.7/C-10 | 候補2 `（HP 10/20…）` | 通過 | 同上。H の内語。地の文・現地人への露出なし |

意味判断: Blocker 0 / Major 0 / Warning 0。

## 総合判定: **PASS**（CODE 通過 + 意味判断すべて通過）

- ドラマ軸メモ（参考・drama_checklist は別系）: ターン=「子どもの玩具の石」→「観測する断片」の反転（I-D1）。開いた問い=石は誰の観測か／理とは（I-D2、OL 敷設）。得た＝失った=どの選択も何かを差し出す構造（I-D5）。感情は行動・沈黙で提示（I-D4）。
