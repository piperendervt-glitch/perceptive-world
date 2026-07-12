# Perceptive World

Perceptive Worldは、同じ初期状態・seed・canonical action列から同じ結果を再現する、決定論的なgamebook／TRPG engineです。現在の`main`はPhase C完了点（`322ff1d`）であり、遊べる検証用sessionと、その挙動を固定するpresentation、record/replay、save/loadの境界を備えています。

完成済みゲームや2D／3D clientではありません。LLMも現在のcanonical stateや判定を操作せず、将来追加し得る非canonical narration層としてのみ想定しています。

## 現在の実装状況

- Console UIと60列×20行を最低表示契約とするfixed-screen terminal UI
- engine stateから生成するimmutableな`RenderSnapshot`
- raw入力を副作用なしで分類・解決するinput resolver
- village、decision、combatを通る決定論的session flow
- 解決済みeventを逐次処理するcanonical village event flow
- stableなWorldObject IDと注目対象（focus）
- versioned record/replayとsave/load
- 複数scenarioをYAMLから読み込む共通engine

Phase C受入れ時のcommit `322ff1d`では、full suiteの322 tests、legacy envoy replay、version 1 focus replayがすべて成功しています。この件数は当該commitの受入れ記録であり、将来も固定される仕様ではありません。

## 主な設計原則

- 判定、状態遷移、乱数消費はengineが所有する。
- UIはraw入力をcanonical eventへ解決し、engineは解決済みeventを再検証する。
- live playとreplayは同じsession flowとvalidation経路を使う。
- engine stateとpresentation modelを分離し、TUIはsnapshotを描画するだけでstateを変更しない。
- record、save、`GameState.snapshot()`は目的の異なるschemaとして分離する。
- TUIは安定したdebug／reference clientとして維持し、将来のclientも同じengineを利用できる構造にする。

## 実行環境とセットアップ

scenario loaderはPyYAMLを使用します。

```text
pip install pyyaml
```

repository rootで以下のcommandを実行してください。

## セッションの起動

通常のConsole UI:

```text
python -B -m trpg_core.session --scenario goblin --seed 7
```

Fixed-screen terminal UI:

```text
python -B -m trpg_core.session --scenario goblin --seed 7 --ui tui
```

利用可能なoptionは実行環境で確認できます。

```text
python -B -m trpg_core.session --help
```

## 操作

Sessionでは表示された選択肢、village移動、探索、戦闘commandを使用します。戦闘commandは`attack`、`magic`、`herb`、`flee`です。

現在sceneの対象には次のfocus commandを使用できます。

```text
focus next
focus prev
focus clear
```

`WorldObjectId`はscenario IDとlocal IDからなる表示非依存のstable IDです。`WorldObjectSpec`が対象のkind、label、sceneとの関係を定義し、`FocusState`はplayer locationと独立して現在の注目対象だけを保持します。現在はmap locationをWorldObjectとして公開し、current sceneに属する対象をfocus候補にします。

Focusのset／clearはturnを進めず、RNGも`state.log`も変更しません。location移動時にはfocusをclearします。UIはraw IDではなく対象labelを表示し、focusがなければ`注目: なし`と表示します。

Client入力の方角や`focus next`／`focus prev`はclient側で解決されます。Engineへ渡るcanonical village eventは、概念上次の5種類です。

- 解決済みWorldObject IDへの移動
- canonical explore keyによる探索
- villageからの出発
- 解決済みWorldObject IDへのfocus設定
- focus解除

実装上は`MoveToLocationAction`、`ExploreAction`、`DepartAction`、`SetFocusAction`、`ClearFocusAction`に対応します。Raw direction、表示label、menu index、GameStateやGameMapそのものはcanonical eventに保存しません。

## Record / Replay

Record formatのcurrent versionは`1`です。`format_version`がないfixtureはlegacy version `0`として読みます。Version 1のchoiceは表示labelではなくcanonical keyです。Version 0は既存fixtureとの互換性のためlegacy label解決を維持します。

録画command:

```text
python -B -m trpg_core.record --scenario goblin --seed 7 --play --out session.json
python -B -m trpg_core.record --scenario goblin --seed 7 --inputs inputs.txt --out session.json
```

Replay command:

```text
python -B -m trpg_core.replay session.json
python -B -m trpg_core.replay --mode state session.json
```

Canonical tokenの例:

```text
move-to:envoy:location/teahouse
focus:set:envoy:location/teahouse
focus:clear
explore:rapport
depart
choice:hear
combat:attack
```

Raw direction、`focus next`／`focus prev`、表示label、menu indexはversion 1のcanonical recordへ入りません。Replay終了時には未消費tokenがないことも検査します。

Version 1 fixtureは任意の`expected_focus_trace`で、focus set／clear後のauthoritative state由来traceを検証できます。これはreplay expectationであり、`GameState`、snapshot、saveのfieldではありません。`focus_play_v1.json`は13 input tokenをすべて消費し、10件の`state.log` entryを再現します。CLIの`events`表示はinput token数ではなく`state.log` entry数です。

## Save / Load

Save formatのcurrent versionも`1`ですが、record format versionとは独立したschemaです。

- Version fieldなし、または明示的な`0`はlegacy saveとして扱う。
- Version 1は`focused_object_id`をcanonical stringで保存する。
- Focusがない場合は`focused_object_id: null`とする。
- Legacy version 0のload後はfocusなしになる。
- Scenario不一致、malformed ID、scene外またはstaleなfocusを拒否する。

Loadは一時stateとmapでvalidationを完了してからlive stateへ反映します。不正なloadでstate、focus、RNG、mapを部分的に変更しません。Focus fieldはsave documentのmetadataであり、既存の`GameState.snapshot()` schemaには追加されていません。

対話sessionでは次のmeta commandを使用します。

```text
save <name>
load <name>
```

## テスト

Full suite:

```text
python -B -m pytest -p no:cacheprovider
```

主要な個別回帰の例:

```text
python -B -m pytest -p no:cacheprovider tests/test_world.py
python -B -m pytest -p no:cacheprovider tests/test_focus_engine.py
python -B -m pytest -p no:cacheprovider tests/test_record_replay.py
python -B -m pytest -p no:cacheprovider tests/test_save_load.py
```

Repositoryに同梱されたversion 1 acceptance fixtureは次のcommandで確認できます。

```text
python -B -m trpg_core.replay tests/fixtures/focus_play_v1.json
```

## アーキテクチャ概要

```text
raw input
  -> pure input resolver
  -> canonical controller event
  -> shared engine validation / transition
  -> GameState
  -> RenderSnapshot
  -> Console / fixed-screen TUI

canonical event stream
  -> record codec
  -> versioned fixture
  -> replay through the same engine path
```

主なmodule:

- `trpg_core/session.py`: session flow、state transition、save/load
- `trpg_core/input_actions.py`: raw入力とcanonical village eventの境界
- `trpg_core/world.py`: WorldObjectとFocusState
- `trpg_core/presentation.py`: neutral presentation snapshot
- `trpg_core/tui.py`: fixed-screen terminal renderer
- `trpg_core/record.py`、`record_codec.py`、`replay.py`: versioned record/replay

## 現在の制限

次の機能は現在の`main`には未実装です。

- visibility／hidden fact runtime
- attention／LOD
- Observe／Inspect action
- trace／memory
- background job queue
- PlayerPosition
- 2D／3D rendererやclient
- LLM narration
- natural-language action proposal

Windows端末では、CLIの日本語help表示が端末の文字コード設定に影響される場合があります。

## 今後の計画

次に予定している境界は、visibility／hidden-factのdomain contractです。現在の`main`で利用可能な機能としては扱っていません。Provider framework、runtime discovery、LODや観察actionは、その境界より後の検討事項です。
