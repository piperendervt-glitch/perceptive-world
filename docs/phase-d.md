# Phase D: Deterministic LOD and visibility

Phase Dは、current sceneのvisibility、focus対象へのattention、決定論的LOD、表示可能factsのprojection、runtime永続化、record/replayを一つの縦切りとして接続します。

## Phase構成

### D-0: Visibility

- `WorldObjectVisibility`が`exists_in_scene`、`perceived`、`focus_candidate`を保持する。
- Current scene queryはsceneに存在するobjectだけを返す。
- Focus候補は`exists_in_scene and perceived and focus_candidate`で抽出する。
- Exact `WorldObjectId`を使用し、labelやpartial IDへfallbackしない。
- Hidden factsをpresentationへ渡さない。

### D-1: LOD model

- `ObjectLodSpec`がobject IDとattention thresholdsを定義する。
- `ObjectAttentionState`がnon-negativeなattentionを保持する。
- `ObjectLodState`がunlocked capを保持する。
- Current LODはattention、cap、specのmax LODから導出する。

### D-2: Pure updates

- Observe policyはattentionを1増やす。
- Inspect policyはattentionを2増やす。
- Unlockはcapを単調に更新する。
- Attentionはclampせず、current LODの導出側でmax LODを適用する。
- Pure updateはwall-clock、FPS、RNGを参照しない。

### D-3: Ancient well content

`goblin:location/well`をLOD 0〜3のvertical sliceとして定義します。

```text
thresholds = (0, 1, 3, 6)
```

| LOD | 新たに公開される情報 |
|---:|---|
| 0 | 井戸らしい形 |
| 1 | 石造り、古い |
| 2 | 新しい滑車、擦れた縄 |
| 3 | 消えかけた紋章 |

Visible factsは累積です。`mark=faded_emblem`はLOD 3より前にはprojectionされません。

### D-4: Canonical actions

- `ObserveFocusedObjectAction`
- `InspectFocusedObjectAction`
- `ApplyLodUnlockAction`

Engine dispatcherはauthoritativeなfocus、focus候補、current scene object IDsからcontextを構築します。Live controllerとreplayは同じdispatcherを通ります。

Observe／Inspectはfocus対象だけを更新し、turn、RNG、HP／MP、map、focus、`state.log`を変更しません。Invalid actionはruntimeを含む全stateを変更せず拒否します。

### D-5: Presentation and TUI

Presentationはfocused objectとruntimeからcurrent LODを導出し、そのLODでvisibleなfactsだけを`RenderSnapshot`へ投影します。

TUIはsnapshotだけを参照します。次の情報は通常表示しません。

- raw object ID
- fact key／raw value
- hidden／future facts
- attention、cap、threshold全体

Fixed-screen contractは60列×20行を最低表示条件とします。

### D-6: Runtime, save, and replay

`GameState`がsessionごとに独立した`LodRuntimeState`を所有します。Runtime entryはobject ID、attention、unlocked capだけを保持し、current LODやfactsは保持しません。

Live inputとしてexact commandの`observe`と`inspect`を受理します。Human-facingなunlock commandはありません。

## Save format v2

LOD runtime payload:

```json
{
  "object_id": "goblin:location/well",
  "attention_level": 3,
  "unlocked_lod_cap": 3
}
```

`current_lod`、facts、labels、thresholds、content specは保存しません。Save v0／v1はempty runtimeへmigrationします。Validation完了前にlive stateへ反映しないため、invalid loadはatomicです。

## Record format v2

Canonical LOD token:

```text
observe
inspect
lod-unlock:<object-id>:<target-cap>
```

Unlock tokenはobject ID内の`:`と`/`を保持できるよう、capをrightmost delimiterで分離します。Malformed ID、negative cap、non-canonical decimal、unknown tokenを拒否します。

`expected_lod_trace`はaccepted canonical village event後のruntime tupleを検証します。各objectについて次を保持します。

- exact object ID
- `attention_level`
- `unlocked_lod_cap`
- derived `current_lod`

Hidden facts、presentation labels、content specはtraceへ含めません。

## Backward compatibility

- Save format v0／v1を読み込み可能。
- Record format v0／v1を再生可能。
- Legacy envoy fixtureを変更しない。
- Focus v1 fixtureをversion 1のまま維持する。
- LOD v2 fixtureは独立したtracked fixtureとして保持する。

## Acceptance

自動受入れで次を確認しています。

- Full regression suite
- legacy envoy replay
- focus v1 replayの連続実行
- LOD v2 replayの連続実行
- LOD progression `0 → 1 → 2 → 2 → 3`
- LOD 3以前のhidden mark非公開
- save/loadによるattention、cap、focus、derived LODの復元
- temporary record/replayの決定論的一致
- focusなしObserve／Inspectのatomic rejection
- SetFocus／ClearFocusだけではattentionが変化しないこと
- CLI helpとmodule import

Phase D automated acceptanceはPASSです。

Windows PowerShell実TTY上のmanual fixed-screen TUI acceptanceでも、次を確認済みです。

- `--ui tui`でfixed-screen TUIが起動する。
- 古井戸へ移動し、`focus next`でLOD 0を表示する。
- `observe`／`inspect`によりLODが`0 → 1 → 2 → 2 → 3`と進む。
- `消えかけた紋章`はLOD 3まで表示されない。
- focusとturn 0を維持する。
- raw object ID、fact key、fact valueを表示しない。
- map、action領域、固定画面が正常に描画される。

Phase D manual real-TTY acceptanceはPASSです。したがってPhase D acceptanceはPASSです。

## Phase Eへ残す境界

- `PlayerPosition`
- movementとfocusの2D接続
- trace LOD
- memory system
- minimal 2D client
- 3D renderer
- LLM narration／input mapping

これらをPhase Dで先行実装しません。Phase D acceptanceは完了しているため、次工程のPhase E-0へ進行可能です。
