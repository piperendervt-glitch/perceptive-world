"""test_fixtures.py — 汎用回帰: tests/fixtures/ の全フィクスチャを replay して一致検証.

「シナリオ+入力列+ログ」のフィクスチャを自動収集し、それぞれ再生して expected_log と
完全一致するかを検証する。seed=7 ゴブリンも thief も、この同じ枠組みで回帰する。

    python -m pytest tests/test_fixtures.py     # pytest
    python tests/test_fixtures.py               # 直接実行（pytest 不要）

LLM は一度も呼ばない。
"""

from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from trpg_core.replay import (  # noqa: E402
    game_state_events,
    is_game_state,
    load_fixture,
    is_fixture,
    progression_events,
    replay_fixture,
)
from trpg_core.record import fixture_from_inputs  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _all_fixtures():
    """フィクスチャ形式（新形式）のファイルだけ集める。旧 session_7.json（list）は除外。"""
    found = []
    for path in sorted(glob.glob(os.path.join(FIXTURE_DIR, "*.json"))):
        try:
            data = load_fixture(path)
        except json.JSONDecodeError:
            continue
        if is_fixture(data):
            found.append((os.path.basename(path), data))
    return found


# ---------------------------------------------------------------------------
# 1) 全フィクスチャを full モードで replay して完全一致
# ---------------------------------------------------------------------------

def test_all_fixtures_replay_full():
    fixtures = _all_fixtures()
    assert fixtures, "フィクスチャが1つも無い"
    for name, fx in fixtures:
        ok, actual, diff = replay_fixture(fx, mode="full")
        assert ok, f"{name}: full 不一致 -> {diff}"
        assert len(actual) == len(fx["expected_log"]), f"{name}: 件数不一致"


# ---------------------------------------------------------------------------
# 2) state モード（描写除外）でも一致（今は描写イベントが無いので full と同じ）
#    Step 3 で type=narration を足しても、この経路が描写を除外して比較できる。
# ---------------------------------------------------------------------------

def test_all_fixtures_replay_state():
    for name, fx in _all_fixtures():
        ok, actual, diff = replay_fixture(fx, mode="state")
        assert ok, f"{name}: state 不一致 -> {diff}"


# ---------------------------------------------------------------------------
# 3) 録画→再生のラウンドトリップ（inputs から expected_log を再生成すると一致）
# ---------------------------------------------------------------------------

def test_record_replay_roundtrip():
    for name, fx in _all_fixtures():
        if fx.get("format_version") in {1, 2, 3, 4, 5}:
            ok, actual, diff = replay_fixture(fx, mode="full")
            assert ok and actual == fx["expected_log"], f"{name}: v1 replay不一致 -> {diff}"
            continue
        regenerated = fixture_from_inputs(
            fx["scenario"], fx["seed"], fx["inputs"],
            respawn=bool(fx.get("respawn", False)),
        )
        assert regenerated["expected_log"] == fx["expected_log"], \
            f"{name}: 録画→再生のラウンドトリップが不一致"


def test_protected_envoy_fixture_remains_legacy_v0():
    path = os.path.join(FIXTURE_DIR, "envoy_play.json")
    fx = load_fixture(path)
    assert "format_version" not in fx
    assert len(fx["inputs"]) == 4
    assert len(fx["expected_log"]) == 10
    ok, actual, diff = replay_fixture(fx, mode="full")
    assert ok and actual == fx["expected_log"], diff


def test_focus_v1_fixture_is_canonical_and_has_focus_expectation():
    fx = load_fixture(os.path.join(FIXTURE_DIR, "focus_play_v1.json"))
    assert fx["format_version"] == 1
    assert fx["expected_focus_trace"] == ["envoy:location/teahouse", None]
    verbs = tuple(token.split(":", 1)[0] for token in fx["inputs"])
    assert {"move-to", "focus", "explore", "depart"} <= set(verbs)
    assert all(not token.startswith(("north", "south", "east", "west"))
               for token in fx["inputs"])
    ok, actual, diff = replay_fixture(fx, mode="full")
    assert ok and actual == fx["expected_log"], diff


def test_lod_v2_fixture_reaches_final_lod_with_canonical_traces():
    fx = load_fixture(os.path.join(FIXTURE_DIR, "lod_play_v2.json"))
    assert fx["format_version"] == 2
    assert fx["inputs"].count("observe") == 2
    assert fx["inputs"].count("inspect") == 2
    assert fx["expected_focus_trace"] == ["goblin:location/well"]
    assert fx["expected_lod_trace"][-1] == [{
        "object_id": "goblin:location/well",
        "attention_level": 6,
        "unlocked_lod_cap": 3,
        "current_lod": 3,
    }]
    first = replay_fixture(fx, mode="full")
    second = replay_fixture(fx, mode="full")
    assert first == second
    assert first[0] and first[1] == fx["expected_log"]


def test_spatial_v3_fixture_replays_twice_with_position_trace():
    fx = load_fixture(os.path.join(FIXTURE_DIR, "spatial_play_v3.json"))
    assert fx["format_version"] == 3
    assert fx["inputs"].count("move-player-to:2,2") == 1
    assert fx["expected_position_trace"][0] == {"x": 1, "y": 2}
    assert fx["expected_position_trace"][-1] is None
    assert len(fx["expected_position_trace"]) == len(fx["expected_lod_trace"])
    first = replay_fixture(fx, mode="full")
    second = replay_fixture(fx, mode="full")
    assert first == second
    assert first[0] and first[1] == fx["expected_log"]


def test_scene_spatial_v4_fixture_uses_catalog_entry_position_and_replays_twice():
    fx = load_fixture(os.path.join(FIXTURE_DIR, "scene_spatial_play_v4.json"))
    assert fx["format_version"] == 4
    assert fx["inputs"][:2] == [
        "move-player-to:3,1", "move-to:goblin:location/well",
    ]
    assert fx["expected_position_trace"][:2] == [
        {"x": 3, "y": 1}, {"x": 3, "y": 3},
    ]
    first = replay_fixture(fx, mode="full")
    second = replay_fixture(fx, mode="full")
    assert first == second
    assert first[0] and first[1] == fx["expected_log"]


def test_story_spatial_v5_fixture_replays_twice():
    fx = load_fixture(os.path.join(FIXTURE_DIR, "story_spatial_play_v5.json"))
    assert fx["format_version"] == 5
    first = replay_fixture(fx, mode="full")
    second = replay_fixture(fx, mode="full")
    assert first == second
    assert first[0] and first[1] == fx["expected_log"]


# ---------------------------------------------------------------------------
# 4) ゲーム状態イベントと描写イベントの区別（Step 3 で描写を比較除外する準備）
# ---------------------------------------------------------------------------

def test_event_classification():
    for name, fx in _all_fixtures():
        log = fx["expected_log"]
        # 今は全イベントがゲーム状態（描写イベントは presenter 側でログ外）
        assert all(is_game_state(e) for e in log), f"{name}: 予期せぬ描写イベント"
        assert game_state_events(log) == log, f"{name}: state 抽出が全件と一致しない"
        # 判定・数値・進行の核が含まれている（回帰の意味がある）
        assert progression_events(log), f"{name}: 進行イベントが無い"


# ---------------------------------------------------------------------------
# 5) goblin_seed7 は従来の seed=7 参照（session_7.json）と同一の 55 events
#    ＝汎用フレーム経由でも既存回帰が保たれている証拠。
# ---------------------------------------------------------------------------

def test_goblin_seed7_matches_canonical():
    fx = load_fixture(os.path.join(FIXTURE_DIR, "goblin_seed7.json"))
    canonical = load_fixture(os.path.join(FIXTURE_DIR, "session_7.json"))
    assert fx["scenario"] == "goblin" and fx["seed"] == 7
    assert fx["expected_log"] == canonical, "goblin_seed7 が session_7.json と不一致"
    assert len(fx["expected_log"]) == 55
    ok, actual, diff = replay_fixture(fx, mode="full")
    assert ok and actual == canonical, f"replay が canonical と不一致 -> {diff}"


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {t.__name__}: {e}")
    print()
    print("FIXTURES:", "PASS" if failed == 0 else f"FAIL ({failed})")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_all())
