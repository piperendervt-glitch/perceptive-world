# consistency-playtest-01-s2-d4-success_with_cost — 整合性QA レポート

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
- 小片パック: `pending-llm-playtest-01-s2-d4-success_with_cost.md`
- 想定 LLM 判断数: **8**（Claude Code セッション内で判定）

## 総合判定: **PENDING-LLM（CODE OK、意味判断待ち）**
