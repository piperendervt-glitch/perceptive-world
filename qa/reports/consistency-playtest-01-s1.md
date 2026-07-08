# consistency-playtest-01-s1 — 整合性QA レポート

生成: qa_run.py（Q4 / 道A・外部API不使用）。CL4 で D-clarity を統合。

## CODE 判定（決定論・qa_deterministic）

| 項目 | 判定 | 理由 |
|---|---|---|
| C-9.3 | 通過 | status_delta is empty; nothing to apply. |
| C-9.6 | 通過 | status_delta is empty. |
| C-11.1 | 通過 | All option.requires satisfiable against canon. |
| C-11.3 | 通過 | option count=3 in [2, 4]. |

## 早期FAIL: なし

- CODE 段 通過。意味判断は **pending** を読んで統合。
- 小片パック: `pending-llm-playtest-01-s1.md`（想定 10 判断: C 系 4 + D-clarity 6）

## 意味判断（Claude Code セッション内・道A / 外部API不使用）

### 整合性（C 系）

| 項目 | 小片 | 判定 | 理由 |
|---|---|---|---|
| C-11.4 | A/B/C の intended_shift | 通過 | 隠蔽維持 / 魔力・露見の喪失 / 関係変質 と、動く価値軸も帰結も相異なる（飾りではない） |
| C-11.2 | option A（理へ繋がる糸を手放す） | 通過 | 「手を引く」選択で理を破る・歪める行為ではない。コードは「理」語で機械フラグ→意味判断で非干渉と確定 |
| C-9.7/C-10 | 候補1 `（残り MP 2…）` | 通過 | H の括弧内内語。転生者の知覚で、女には示していない（I-4 保持） |
| C-9.7/C-10 | 候補2 `（HP 10/20…）` | 通過 | 同上。H の内語。地の文・現地人への露出なし |

### D-clarity（明瞭さ・I-D8/I-D9）— open_loops 照合先: OL-p01「読める刻印は観測の痕跡か」

| # | 小片 | kinds / subj | 判定 | 理由（謎照合） |
|---|---|---|---|---|
| a | 「彫りが揺れて見えた」 | supernatural / subj=True | 通過 | H の主観（見えた）。刻印が読める現象＝OL-p01 の謎に紐づく密度 |
| b | 「線がひとりでに順序を持ち…」 | supernatural / subj=False | 通過 | 刻印が自ら読める形へ向かう＝OL-p01（観測の痕跡）そのもの。謎の中核 |
| c | 「意味になる前のもの」 | supernatural / subj=False | 通過 | 刻印の正体＝OL-p01。意図した謎の核 |
| **d** | **「（この石、こちらを見ている）」** | supernatural / subj=False | **通過** | **【正解6】** 観測する石＝OL-p01。登録された謎に直接紐づく（H 内語で主観帰属も明示） |
| **e** | **「…彫りの底まで確かめられる…」** | literal_breaking(の底) | **Warning** | **【正解1】** 謎に無関係な骨の不明瞭。「彫りの底」で何を確かめるか像がぼやける（指示対象不明） |
| **f** | **「走って逃げる目はない」** | literal_breaking(目はない) | **Warning** | **【正解2】** 字義が壊れた慣用（走って逃げる“目”が字義で成立しない）。謎に無関係 |

**Scene1 D-clarity: Warning 2（e/f＝正解1,2）/ 通過 4（含 正解6=d）。詩的密度 a/b/c は謎の周りに集中しており I-D8 適合。**

## 総合判定: **PASS（CODE 通過 + 整合性すべて通過）／ D-clarity は骨の不明瞭 2 件を Warning（書き直し対象）**

- ドラマ軸メモ（参考・drama_checklist は別系）: ターン=「子どもの玩具の石」→「観測する断片」の反転（I-D1）。開いた問い=石は誰の観測か／理とは（I-D2、OL-p01 敷設）。得た＝失った=どの選択も何かを差し出す構造（I-D5）。
