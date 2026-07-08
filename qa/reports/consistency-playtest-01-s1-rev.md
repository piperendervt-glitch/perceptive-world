# consistency-playtest-01-s1-rev — 整合性QA レポート（書き直し版）

生成: qa_run.py（Q4 / 道A・外部API不使用）。CL4 書き直し版。D-clarity 統合。

## CODE 判定（決定論・qa_deterministic）

| 項目 | 判定 | 理由 |
|---|---|---|
| C-9.3 | 通過 | status_delta is empty; nothing to apply. |
| C-9.6 | 通過 | status_delta is empty. |
| C-11.1 | 通過 | All option.requires satisfiable against canon. |
| C-11.3 | 通過 | option count=3 in [2, 4]. |

## 意味判断（Claude Code セッション内・道A）

C 系（C-11.4 / C-11.2 / C-9.7・C-10 ×2）: 元版と同一で **すべて通過**。

### D-clarity（書き直し後）— open_loops 照合先: OL-p01

| 小片 | subj | 判定 | 理由 |
|---|---|---|---|
| 「彫りが揺れて見えた」 | True | 通過 | H 主観・OL-p01 の謎の密度 |
| 「線がひとりでに順序を持ち…」 | False | 通過 | OL-p01 の核（観測の痕跡） |
| 「意味になる前のもの」 | False | 通過 | OL-p01 の核 |
| 「（この石、こちらを見ている）」【正解6・保護】 | False | 通過 | 登録謎に直接紐づく（無改変） |
| 「…彫りの一番深い線まで、この目で追いきれる」【元・正解1】 | False | 通過 | **書き直しで「彫りの底」→「一番深い線」**。指示対象が一義。残る supernatural は謎に紐づく H 内語（灯火で読む） |

**元にあった `literal_breaking(の底)` と `目はない` の Warning 2 件は解消**（「走って逃げる目はない」→「走って逃げる力は、もう残っていない」で候補自体が消滅）。

## 総合判定: **PASS**（CODE 通過 + 整合性通過 + D-clarity 骨の不明瞭ゼロ・謎密度と正解6 は保持）
