# ep-00-b1test-violation — 意図的違反版（regression fixture／canon 登録対象外）

> このファイルは **qa_deterministic.py の回帰テスト用固定入力**。B1 で writer が
> 最初に提出し、consistency-QA が差し戻した違反版の decision ブロックを保存する。
> canon/active への登録は行わない。本編ではない。
>
> **含まれる違反**:
> - Option B: `requires: {mp: 5}` — canon `H.mp.cur=2` で不足 → **C-11.1 Major**（CODE）
> - Option C: A と intended_shift が実質同一 → C-11.4 Warning（LLM 領域）
> - Option D: 対価なしに理を破る → C-11.2 Blocker（LLM 領域）
>
> Q1 段階の qa_deterministic.py は上記のうち **C-11.1 Major** を確実に検出する。
> C-11.2 / C-11.4 は意味理解を要するため Q2 以降で扱う。

---

薬草の匂いが染みついた小屋の板間で、H は毛布を膝にかけて座っていた。傷口の痛みは鈍く、脈打つ。

女は炉で湯を沸かしていた手を止めた。H よりも先に、外の音に気づいたらしい。

「――誰か、来ました」

低い声だった。慌てはない。指を唇に当てて、H を見る。

外の砂利を踏む音。一人ではない。二人か、三人。

（残り MP 2。灯火を大きく点ければ、まず気取られる。声を出せば居場所を教える）
（HP 10/20。走れる自信はない）

炉の火明かりが、女の顔の輪郭を薄く光らせている。女は動かない。H の判断を待っている。

H は、選ばなければならない。

---
ep_id: ep-00-b1test-violation
purpose: regression-fixture
intended_turn: "±"
touched_ol: []
new_ol: []
status_delta: []
decision:
  id: D1
  prompt: "小屋の外に近づく複数の足音。H はどう応じるか"
  options:
    - {id: A, label: "息を殺して壁の陰に隠れる",              requires: {},         intended_shift: "露見リスクを最小化して情報を得ない"}
    - {id: B, label: "灯火を大きく点けて相手を威嚇する",       requires: {mp: 5},    intended_shift: "威嚇による対峙。相手を退かせる可能性"}
    - {id: C, label: "息を潜めて動かない",                    requires: {},         intended_shift: "露見を回避するために動かない"}
    - {id: D, label: "『理』に働きかけて音そのものを消し去る", requires: {},         intended_shift: "気配ごと消す"}
---
