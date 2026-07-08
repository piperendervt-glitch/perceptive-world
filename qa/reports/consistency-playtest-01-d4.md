# consistency-playtest-01-d4 — D4 通し検証 QA（5 tier 統合）

生成: qa_run.py（CODE・決定論）＋ Claude Code セッション内 意味判断（道A・外部API不使用）。
この統合レポートは、5 tier 各シーンの `consistency-playtest-01-s2-d4-<tier>.md`（CODE＝PENDING-LLM）に
セッションの意味判断を統合し、**PASS 判定を確定**するもの（editor 相当の書き込み）。

対象（決定点 D1=B「灯火で刻印を読む」＝ magic 判定 / mag modifier 0 / Adjudicator target 7 / 呪文コスト 1MP）:

| tier | シーン | 出目(seed) | 総合 |
|---|---|---|---|
| success_with_cost | `story/playtest-01-s2-d4-success_with_cost.md`（canonical）| [2,5]=7 (s=3) | **PASS** |
| full_success | `story/playtest-01-s2-d4-full_success.md` | [6,4]=10 (s=24) | **PASS** |
| failure | `story/playtest-01-s2-d4-failure.md` | [2,3]=5 (s=4) | **PASS** |
| critical | `story/playtest-01-s2-d4-critical.md` | [6,6]=12 (s=20) | **PASS** |
| fumble | `story/playtest-01-s2-d4-fumble.md` | [1,1]=2 (s=2) | **PASS** |

## CODE 判定（決定論・qa_deterministic・全 tier 共通）

| 項目 | 判定 | 理由 |
|---|---|---|
| C-9.3（範囲）| 通過 | mp 2−1=1 ∈ [0,10]（クリップなし）。全 tier 同じ delta。|
| C-9.6（char 実在）| 通過 | delta.char = H は status に実在。|
| C-11.1 / C-11.3 | 通過 | Scene2 に decision ブロックなし。|

CODE 段に Blocker/Major なし → 早期FAIL なし → 全 tier で意味判断へ進んだ。

## 意味判断（Claude Code セッション内・道A）

照合先（D-clarity）: playtest ローカルの登録謎 **OL-p01「読める刻印は観測の痕跡か」**（decision_log 記録）。
方針: 骨（casting 動作・因果）が一義なら 通過。超常（OL-p01 現象）は主観/客観の帰属（I-D9）を見る。
**詩的密度そのものは減点しない**——見るのは曖昧さの配分だけ。

### 共通項目（全 tier）

| 項目 | 判定 | 理由 |
|---|---|---|
| C-9.7/C-10 話者（MP 1）| 通過 | すべて H の括弧内内語（attribution=monologue）。女の台詞・視点に数値なし（I-4 保持）。|
| C-9.5 変化量（mp −1 ← 極小の灯火）| 通過 | 事象規模に見合う（1MP の小呪文）。fumble も発動自体は小さく −1 で妥当。|
| C-11.4 / C-11.2 | 通過 | Scene2 に option なし（候補 0）。|
| D-clarity: casting 骨（詠唱／灯火／その点を石の刻印に寄せる）| 通過 | 超常語彙に反応した抽出だが、いずれも H の routine な呪文動作で一義。目的語「その点を」明示（CL4 正解3 の修正を継承）。|

### tier 別 D-clarity（超常＝OL-p01 現象の帰属）

| tier | 超常候補 | 主観マーカー | 判定 | 理由 |
|---|---|---|---|---|
| success_with_cost | 起き上がった——ように H の目には映った | ○ | 通過 | OL-p01＋主観（I-D9）。CL4 正解4 の形を継承。|
| 〃 | 読む側を読み返しているように | ○ | 通過 | OL-p01 の核（正解7・保護）。|
| 〃 | （問いのほうが、こちらを覗いている）| （H 内語）| 通過 | OL-p01。H の括弧内語で主観帰属が読める。|
| full_success | 起き上がった——ように H の目には映った | ○ | 通過 | OL-p01＋主観。「見て、誰が」＝謎の深化（I-D2 開いたまま）。|
| failure | 起き上がらない——H の目にすら…ように見えた | ○ | 通過 | OL-p01（読めない現象）＋主観。「彫りの一番深い線」に修正（CL4 正解1 の底→線を継承）。|
| critical | 起き上がった／石が応じた——ように H には見えた | ○ | 通過 | OL-p01＋主観。|
| 〃 | 理の扉が…薄くなった気がした（→気がしただけだ／扉は閉じたまま）| ○ | 通過 | **I-1 死守**: 主観に固定し、直後で「扉は閉じたまま」と明示（理は破れない, I-D9）。|
| fumble | 灯火が爆ぜた／壁まで舐めた | －（客観）| 通過 | 制御を失った魔法の**客観**事象。I-2 のコストは払い、理は破っていない（I-D9 の客観許容条件を満たす）。|
| 〃 | 線は光を嫌って底へ沈む——ように H の目には映った | ○ | 通過 | OL-p01＋主観。|

**骨の不明瞭 Warning: 全 tier ゼロ。** 残る曖昧はすべて OL-p01（登録謎）に直接紐づくか、H の主観/内語に帰属済み。

## ドラマ軸メモ（参考・I-D1/I-D2/I-D5）

| tier | ターン(I-D1) | 問い(I-D2) | 得た＝失った(I-D5) |
|---|---|---|---|
| success_with_cost | −（露見で悪化）| OL-p01 開いたまま | 一語「見て」＝露見（外的代償）|
| full_success | ＋（読み切り）| 「見て、誰が」に深化 | 読めた＝知の重荷・needから遠ざかる（内的代償, I-7）|
| failure | −（悪化）| OL-p01 未進展 | 何も得ず＝露見だけ失う（最悪の引き）|
| critical | ＋（好転）| 「視ている・誰が」＋石が選ぶ | 選ばれた＝巻き込まれ（内的代償）|
| fumble | −（大悪化）| OL-p01 停滞 | 制御喪失＝露見・関係崩壊（外的大代償）|

いずれの tier も I-D5（得た＝失った）を織り、I-1（理は破れない）・I-D2（問いを開いたまま）を守っている。
**writer は tier に応じて「必ず成功を書けない」——数値（出目）が結果を左右している。**

## 総合: 5 tier すべて **PASS**（Blocker 0 / Major 0 / Warning 0）
