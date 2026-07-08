# playtest-01 / D4 — 判定を差し込んだ通し検証（選ぶ→振る→3段階→描写→ログ）

> 目的: playtest-01 の決定点 **D1=B**（灯火で刻印を読む）に判定エンジンを差し込み、
> **選ぶ → 2D6＋修正 → 3段階(＋ゾロ目) → writer が tier を描写 → play_log に構造化記録**
> が通しで動くことを、既知シーンで確認する。**検証専用。canon/active 未登録・canon/status.yaml 未書換。**
> 乱数はコード独占（[[resolve.py]]）。修正値は status 連動（status_resolve.py）。提示・ログは play_log.py。

## 1. 判定の差し込み（決定点 B）

Scene 1 の決定点 D1=B「残る魔力で灯火を極小に灯し、彫りの底を自分の目で読む」を、判定として解決する。

| 要素 | 値 | 根拠 |
|---|---|---|
| action_type | `magic`（魔法的判定）| 灯火の呪文で刻印を読む → mag（status_resolve の対応表）|
| char / 使用能力 | H / `mag` | |
| modifier | **0** | `mag(8) − ABILITY_PIVOT(8)`。**H は血統なし＝mag が基準どまり（I-3）** |
| target | **7** | Adjudicator 裁定「灯火で古い刻印を読む」は中庸。ただし H は補正 0 で余裕がなく、clean success（total≥10）は出目の上振れ頼み＝**低 mag が効く** |
| 呪文コスト | **1 MP** | 「極小の灯火」。playtest の `requires:{mp:1}` と整合。H は mp 2/10 → 発動可、消費後 1/10 |
| MP 充足 | OK | `cur_mp 2 ≥ cost 1`（C-11.1 と整合。不足なら試行不可だった）|

`modifier_from_status` と `resolve_action(mp_cost=1)` の供給で、D1 の `resolve()` は無改変のまま回る。

## 2. 出た tier が Scene2 を左右する（writer は必ず成功を書けない）

同じ選択 B でも、**出目次第で結果が変わる**。各 tier の Scene2 を writer が書き分けた（すべて canon 未登録）。
出目は seed で再現可能（`python status_resolve.py --action magic --char H --target 7 --seed <s>` 相当）。

| tier | 出目(seed) | total vs 7 | Scene2 の帰結 | ファイル |
|---|---|---|---|---|
| **critical**（6-6）| [6,6]=12 (s=20) | 特別な好転 | 三画読み切り＋石が応じる新スレッド・露見なし。**理の扉は閉じたまま(I-1)** | `playtest-01-s2-d4-critical.md` |
| **full_success** | [6,4]=10 (s=24) | 叶う・外的代償なし | 「見て、誰が」まで読み、露見せず。謎は深化・**知の重荷は残る(内的 I-D5)** | `playtest-01-s2-d4-full_success.md` |
| **success_with_cost** ★canonical | [2,5]=7 (s=3) | 叶うが代償(I-D5) | 一語「見て」だけ得て、女に露見。**得た＝失った** | `playtest-01-s2-d4-success_with_cost.md` |
| **failure** | [2,3]=5 (s=4) | 叶わず悪化 | 何も読めず、露見だけした。手がかりゼロ（Director 燃料）| `playtest-01-s2-d4-failure.md` |
| **fumble**（1-1）| [1,1]=2 (s=2) | 特別な悪化 | 灯が暴れ派手に露見、女が怖れて後退＝関係崩壊（大燃料）| `playtest-01-s2-d4-fumble.md` |

**★ canonical playthrough**: 実際に振った出目 seed=3 は **success_with_cost**。
playtest-01 でうまく行っていた「得た＝露見」型が、**ダイス由来で自然発火**した（作為ではなく判定の帰結）。

H の mag=8（modifier 0）だと、target 7 で成功しても代償帯 [7,9] に落ちやすく、clean な full_success（total≥10）は
出目上振れ頼み。**血統のない H の低 mag が、判定分布として不利に効いている**（I-3 が数値で現れる）。

## 3. 構造化ログ（play_log.yaml・動画化の素材）

各判定を `meta/play_log.yaml` に機械可読で記録した（誰が/何を/成否/代償/結果）。D1 の器 `make_log_entry` を
実運用に接続し、resolve を seed 込みで verbatim 内包（＝後で動画に渡せる／再生成できる）。canonical エントリ:

```yaml
- turn: 1  decision_id: D1  chosen: B（…灯火を極小に灯し…）
  char: H  action_type: magic
  dice: [2, 5]  total: 7  target: 7  tier: success_with_cost  modifier: 0
  cost_applied: {mp: 1, id5_fired: true}     # mp=I-2 コスト / id5=I-D5 発火
  consequence: 一語「見て」だけ読めたが露見（得た＝失った, I-D5）。canonical。
  status_delta: [{char: H, change: {mp.cur: -1}, cause: "灯火を灯して石の刻印を読んだ"}]
  scene_ref: story/playtest-01-s2-d4-success_with_cost.md  reveal_dice: true  seed: 3
```

`cost_applied.id5_fired` は success_with_cost でのみ true（他 tier は false）。全 6 エントリを記録（下記）。

## 4. reveal_dice ON / OFF 両方で一巡

`config/play.yaml` の `reveal_dice`（既定 **true**）で player 提示が切り替わる。canonical 判定を両モードで一巡した:

| モード | player が見るもの | play_log |
|---|---|---|
| **ON**（既定・普通の TRPG）| `2D6[2,5]=7 +0 → 7 vs 目標7 … success_with_cost` | dice 記録あり |
| **OFF**（隠しモード）| 「叶うが代償・複雑化を伴う（I-D5）」＝帰結の形だけ。出目は伏せる | **dice=[2,5] を保持** |

writer の散文（Scene2）は **reveal_dice に依存しない**——OFF でも tier の帰結は同じに書く。
**OFF でもログには出目が残る**（内部真実の保持）。play_log の turn 1 に ON/OFF 両エントリを記録済み。

## 5. QA（整合性・ドラマ・明瞭さ）

5 tier すべてを `qa_run.py`（CODE・決定論）に通し、意味判断を Claude Code セッション内（道A・外部API不使用）で下した。

- **CODE**: 全 tier で C-9.3 / C-9.6 / C-11.1 / C-11.3 通過（mp 2−1=1 ∈ [0,10]・早期FAIL なし）。
- **意味判断**: C-9.7/C-10（MP 1 は H 内語・I-4 保持）、C-9.5（−1 は極小灯火に妥当）すべて通過。
- **D-clarity（明瞭さ）**: **骨の不明瞭 Warning は全 tier ゼロ**。超常（OL-p01 現象）は主観マーカーで帰属明示、
  critical の「理の扉」は主観に固定し直後で「閉じたまま」と明示（I-1 死守）、fumble の暴発は客観だが理内（I-2）。
- **ドラマ**: 全 tier が I-D5（得た＝失った）を織り、I-1・I-D2 を守る。

統合レポート: **`qa/reports/consistency-playtest-01-d4.md`（5 tier すべて PASS / Blocker 0・Major 0・Warning 0）**。
各 tier の CODE 詳細は `qa/reports/consistency-playtest-01-s2-d4-<tier>.md`、小片パックは `pending-llm-…-<tier>.md`。

## 6. スコープの明示

- 検証専用。**canon/active 未登録・canon/status.yaml 未書換・meta/engine_state.md 未書換**（playtest ローカル）。
- 本編は量産しない。5 tier の Scene2 は「判定が結果を左右する」ことの実証サンプル。
- 別 tier（canonical 以外）の play_log エントリは turn `1-alt` として、分岐実例（seed 再現可能）を記録したもの。

## まとめ

**2D6＋修正 → 3段階判定（＋ゾロ目）が、出目表示モード付きで「選ぶ→振る→描写→ログ」を通しで動かし、
判定ログが動画化を見据えた構造で残る=普通の TRPG として遊べる土台が完成した。** 修正値は status 連動で、
H の低い mag が判定分布に不利として効き、success_with_cost では「得た＝露見」がダイス由来で自然発火する。
出目は ON で見え OFF で隠れるが、ログには常に完全に残る。Step C（自由記述）・メディア化（動画生成）等の
次段は、**指示があるまで着手しない**。
