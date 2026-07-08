# pending-llm-playtest-01-s2 — 意味判断の小片パック

> qa_run.py が CODE 段通過後に生成。**外部 API は使わない。**
> Claude Code セッションが各小片を読み、重大度を記入する。
> 記入後、判定を qa/reports/consistency-playtest-01-s2.md に統合する（editor 相当）。

想定 LLM 判断数: **2**

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
まるで、読む側を読み返しているように。 （残り MP 1。あと一度きり） （答えじゃない。問いのほうが、こちらを覗いている）
```
meta: {'sentence': '（残り MP 1。あと一度きり）', 'categories': ['mp', 'number'], 'matched': ['MP', '1'], 'attribution_hint': 'monologue', 'sentence_index': 11}
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
