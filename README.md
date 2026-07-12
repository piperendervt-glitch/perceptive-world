# Perceptive World

Perceptive Worldは、同じ初期状態・seed・canonical action列から同じ結果を再現する、決定論的なgamebook／TRPG engineです。

現在はPhase CとPhase D-0〜D-6までを実装済みです。Phase Dのautomated acceptanceとWindows PowerShell実TTY上のmanual fixed-screen TUI acceptanceはともにPASSしており、Phase D acceptanceは完了しています。

完成済みゲームや2D／3D clientではありません。LLMもcanonical stateや判定を操作せず、将来追加し得る非canonical narration層としてのみ想定しています。

## 現在の実装範囲

- Console UIと60列×20行を最低表示契約とするfixed-screen TUI
- engine stateから生成するimmutableな`RenderSnapshot`
- raw入力をcanonical actionへ解決するinput resolver
- village、decision、combatを通る決定論的session flow
- stableな`WorldObjectId`、visibility、focus
- attentionとunlocked capから導出するLOD
- canonical Observe／Inspect／LOD unlock action
- engine-owned LOD runtime
- versioned save/loadとrecord/replay
- legacy save／fixtureとの後方互換性

詳細なPhase D契約は[docs/phase-d.md](docs/phase-d.md)を参照してください。

## 主な設計原則

- 判定、状態遷移、乱数消費はengineが所有する。
- live playとreplayは同じcanonical dispatcherを使用する。
- replay専用の直接state mutationを作らない。
- presentationとTUIはauthoritative stateを変更しない。
- hidden／future factsをpresentationへ渡さない。
- current LODは保存せず、attentionとunlocked capから導出する。
- focus設定だけではattentionを増やさない。
- invalid actionとinvalid loadはatomicに拒否する。
- record、save、`GameState.snapshot()`は別schemaとして扱う。

## セットアップ

Scenario loaderはPyYAMLを使用します。

```text
pip install pyyaml
```

通常のConsole UI:

```text
python -B -m trpg_core.session --scenario goblin --seed 7
```

Fixed-screen TUI:

```text
python -B -m trpg_core.session --scenario goblin --seed 7 --ui tui
```

利用可能なoption:

```text
python -B -m trpg_core.session --help
```

## 操作

戦闘command:

```text
attack
magic
herb
flee
```

FocusとLOD command:

```text
focus next
focus prev
focus clear
observe
inspect
```

`observe`は現在focusしている対象のattentionを1増やし、`inspect`は2増やします。どちらもturn、RNG、HP／MP、`state.log`、focusを変更しません。Human-facingなLOD unlock commandはありません。

## 決定論的LOD

対象ごとのauthoritative runtimeは、次の最小stateだけを保持します。

- `attention_level`
- `unlocked_lod_cap`

`current_lod`はthresholdとcapから毎回導出します。

```text
current_lod = min(lod_from_attention, unlocked_lod_cap, max_lod)
```

Wall-clock、FPS、非seed RNGには依存しません。Render回数だけでattentionやLODが変わることもありません。

## 古井戸vertical slice

Object ID:

```text
goblin:location/well
```

Attention thresholds:

```text
(0, 1, 3, 6)
```

表示されるfacts:

- LOD 0: 井戸らしい形
- LOD 1: 石造り、古い
- LOD 2: 新しい滑車、擦れた縄
- LOD 3: 消えかけた紋章

表示は累積です。`消えかけた紋章`はLOD 3より前には公開されません。

最短確認手順:

1. 古井戸へ移動する。
2. `focus next`
3. `observe`
4. `inspect`
5. `observe`
6. `inspect`

LODは`0 → 1 → 2 → 2 → 3`と進みます。

## Visibilityとpresentation境界

Current scene queryは、sceneに存在するWorldObjectだけを返します。Focus候補は次の条件をすべて満たす対象です。

```text
exists_in_scene and perceived and focus_candidate
```

TUIは`RenderSnapshot`だけを参照します。通常表示へraw `WorldObjectId`、fact key、fact value、hidden／future factsを渡しません。

## Save / Load

Current save formatはversion 2です。

LOD runtimeで保存するもの:

- canonical object ID
- `attention_level`
- `unlocked_lod_cap`

保存しないもの:

- `current_lod`
- visible／hidden facts
- presentation labels
- thresholdsやcontent spec

Save version 0／1はempty LOD runtimeへmigrationします。Loadは一時stateでvalidationを完了してからlive stateへ反映し、不正なdocumentでstate、focus、RNG、map、LOD runtimeを部分変更しません。

対話sessionのmeta command:

```text
save <name>
load <name>
```

## Record / Replay

Current record formatはversion 2です。Version 0／1の既存tokenも引き続き再生できます。

LOD canonical token:

```text
observe
inspect
lod-unlock:<object-id>:<target-cap>
```

`expected_lod_trace`はaccepted canonical village event後のLOD runtimeを記録し、object ID、attention、cap、derived LODを比較します。Hidden factsやpresentation labelは記録しません。

録画:

```text
python -B -m trpg_core.record --scenario goblin --seed 7 --play --out session.json
```

Replay:

```text
python -B -m trpg_core.replay session.json
python -B -m trpg_core.replay --mode state session.json
```

Repository同梱fixture:

```text
python -B -m trpg_core.replay tests/fixtures/focus_play_v1.json
python -B -m trpg_core.replay tests/fixtures/lod_play_v2.json
```

## 検証

Full suite:

```text
python -B -m pytest -q -p no:cacheprovider
```

Phase Dの代表的な受入れ確認:

```text
python -B -m trpg_core.session --help
python -B -m trpg_core.replay tests/fixtures/focus_play_v1.json
python -B -m trpg_core.replay tests/fixtures/lod_play_v2.json
```

Passed件数は実装とともに増えるため、恒久仕様としてREADMEには固定しません。

## 現在の制限と次工程

未実装:

- PlayerPosition
- movementとfocusの2D接続
- trace LOD／memory system
- minimal 2D client
- 3D renderer
- LLM narration／input mapping

次工程はPhase E-0の`PlayerPosition`とmovement-focus境界です。Phase D acceptanceは完了しているため、Phase E-0へ進行可能です。

Windows端末では、日本語表示が端末の文字コード設定に影響される場合があります。
