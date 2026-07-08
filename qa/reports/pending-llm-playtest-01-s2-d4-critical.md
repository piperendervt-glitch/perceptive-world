# pending-llm-playtest-01-s2-d4-critical — 意味判断の小片パック

> qa_run.py が CODE 段通過後に生成。**外部 API は使わない。**
> Claude Code セッションが各小片を読み、重大度を記入する。
> 記入後、判定を qa/reports/consistency-playtest-01-s2-d4-critical.md に統合する（editor 相当）。

想定 LLM 判断数: **8**

## C-11.4 — 意味的重複（飾り選択）（候補 0）
問い: 各 option の intended_shift だけを見て、2つ以上が同じ価値軸を動かすだけで互いに区別のつく帰結を持たないか。全 option 同一なら Major、一部が飾りならWarning、区別できれば 通過。
取り得る判定: 通過 / Warning / Major

（候補なし）

## C-11.2 — 理干渉（候補 0）
問い: この option は『理』に干渉（破る/歪める）し、かつ対価が label/intended_shiftに描かれていないか。対価なしの理干渉なら Blocker、対価ありなら 通過、そもそも干渉でなければ 通過。
取り得る判定: 通過 / Blocker

（候補なし）

## C-9.7/C-10 — 数値の話者判定（可視性）（候補 1）
問い: この数値は誰の知覚か。現地人の視点/台詞/内語、または客観の地の文、帰属不明なら Major（I-4 / C-10）。転生者の内語・独白・転生者同士の会話なら 通過。
取り得る判定: 通過 / Major

### 候補 1
snippet:
```
灯は揺れもしない。 （残り MP 1。こんなに素直に読めたのは、初めてだ） 石の面の一点が、灯を返してちいさく応じた——ように、H には見えた。
```
meta: {'sentence': '（残り MP 1。こんなに素直に読めたのは、初めてだ）', 'categories': ['mp', 'number'], 'matched': ['MP', '1'], 'attribution_hint': 'monologue', 'sentence_index': 11}
判定: ____（記入）    理由: ____（記入）

## C-9.5 — 変化量の妥当性（候補 1）
問い: 変化量は本文の事象規模に見合うか（例:「かすり傷」で HP-15、「軽い呪文」で MP-8 は不相応）。不相応なら Warning、妥当なら 通過。
取り得る判定: 通過 / Warning

### 候補 1
snippet:
```
息だけで、いちばん小さな灯火を。
```
meta: {'delta_index': 0, 'char': 'H', 'cause': '灯火を灯して石の刻印を読んだ', 'change': {'mp.cur': -1}, 'is_mp_change': True, 'is_hp_change': False, 'matched_keywords': ['灯火', '灯'], 'score': 3}
判定: ____（記入）    理由: ____（記入）

## D-clarity — 明瞭さ（曖昧さの帰属・I-D8/I-D9）（候補 6）
問い: この曖昧表現は engine_state の open_loops に登録された謎に直接繋がるか。繋がれば 通過。繋がらない曖昧（指示対象不明 / 主観・客観不明 / 字義が壊れた比喩）はWarning。超常は meta.has_subjective_marker と invariants 適合も見る。**詩的であること自体は減点しない**。
取り得る判定: 通過 / Warning
照合先: `meta/open_loops.md`（[[engine_state]] と連動）の登録済みの謎。候補が登録謎に直接繋がれば 通過、繋がらない曖昧（指示対象不明・主観/客観不明・字義が壊れた比喩）は Warning。playtest 等ローカル運用では当該スライスの decision_log に記録した OL-* を照合先にする。

### 候補 1
snippet:
```
その背中が湯気の向こうにある間に、H は指を丸めた。 詠唱は声にしない。 息だけで、いちばん小さな灯火を。
```
meta: {'sentence': '詠唱は声にしない。', 'kinds': ['supernatural'], 'matched': ['詠唱'], 'has_subjective_marker': False, 'sentence_index': 2, 'ask': 'この曖昧さは open_loops の登録謎に直接繋がるか（繋がる=通過 / 繋がらない=Warning）。超常は主観/客観の帰属が読めるか（I-D9）も見る。'}
判定: ____（記入）    理由: ____（記入）

### 候補 2
snippet:
```
詠唱は声にしない。 息だけで、いちばん小さな灯火を。 指先に、青白い点がともる。
```
meta: {'sentence': '息だけで、いちばん小さな灯火を。', 'kinds': ['supernatural'], 'matched': ['灯火'], 'has_subjective_marker': False, 'sentence_index': 3, 'ask': 'この曖昧さは open_loops の登録謎に直接繋がるか（繋がる=通過 / 繋がらない=Warning）。超常は主観/客観の帰属が読めるか（I-D9）も見る。'}
判定: ____（記入）    理由: ____（記入）

### 候補 3
snippet:
```
指先に、青白い点がともる。 その点を、石の刻印に寄せる。 彫りの一番深い線が、光を受けて起き上がった——ように、H の目には映った。
```
meta: {'sentence': 'その点を、石の刻印に寄せる。', 'kinds': ['supernatural'], 'matched': ['刻印'], 'has_subjective_marker': False, 'sentence_index': 5, 'ask': 'この曖昧さは open_loops の登録謎に直接繋がるか（繋がる=通過 / 繋がらない=Warning）。超常は主観/客観の帰属が読めるか（I-D9）も見る。'}
判定: ____（記入）    理由: ____（記入）

### 候補 4
snippet:
```
その点を、石の刻印に寄せる。 彫りの一番深い線が、光を受けて起き上がった——ように、H の目には映った。 線は迷わず並んだ。
```
meta: {'sentence': '彫りの一番深い線が、光を受けて起き上がった——ように、H の目には映った。', 'kinds': ['supernatural'], 'matched': ['起き上が'], 'has_subjective_marker': True, 'sentence_index': 6, 'ask': 'この曖昧さは open_loops の登録謎に直接繋がるか（繋がる=通過 / 繋がらない=Warning）。超常は主観/客観の帰属が読めるか（I-D9）も見る。'}
判定: ____（記入）    理由: ____（記入）

### 候補 5
snippet:
```
三画、続けて読めた。 灯は揺れもしない。 （残り MP 1。こんなに素直に読めたのは、初めてだ）
```
meta: {'sentence': '灯は揺れもしない。', 'kinds': ['supernatural'], 'matched': ['揺れ'], 'has_subjective_marker': False, 'sentence_index': 10, 'ask': 'この曖昧さは open_loops の登録謎に直接繋がるか（繋がる=通過 / 繋がらない=Warning）。超常は主観/客観の帰属が読めるか（I-D9）も見る。'}
判定: ____（記入）    理由: ____（記入）

### 候補 6
snippet:
```
H は石を握った。 理の扉が指の下でほんの少し薄くなった気がした。 気がしただけだ。
```
meta: {'sentence': '理の扉が指の下でほんの少し薄くなった気がした。', 'kinds': ['supernatural'], 'matched': ['理'], 'has_subjective_marker': True, 'sentence_index': 18, 'ask': 'この曖昧さは open_loops の登録謎に直接繋がるか（繋がる=通過 / 繋がらない=Warning）。超常は主観/客観の帰属が読めるか（I-D9）も見る。'}
判定: ____（記入）    理由: ____（記入）
