from __future__ import annotations

import copy
import json

import pytest

from trpg_core.map import build_map
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import (
    CURRENT_SAVE_FORMAT_VERSION, ConsoleController, GameState,
    make_save_document, parse_save_format_version,
)
from trpg_core.world import location_world_object_id
from trpg_core.lod import ObjectAttentionState, ObjectLodState
from trpg_core.lod_actions import LodRuntimeState, ObjectLodProgress
from trpg_core.spatial import PlayerPosition


def _state():
    return GameState(7, scenario=load_scenario("goblin"))


def _focus(state, location="well"):
    state.transition_location(location)
    object_id = location_world_object_id("goblin", location)
    state.set_focused_object(object_id, focusable_object_ids=(object_id,))
    return object_id


def _fingerprint(state):
    return {
        "snapshot": copy.deepcopy(state.snapshot()),
        "focus": state.focus_state.focused_object_id,
        "rng": state.rng.state(),
        "log": copy.deepcopy(state.log),
        "player_position": state.player_position,
        "completed_village_actions": state.completed_village_actions,
    }


@pytest.mark.parametrize("document,expected", [({}, 0), ({"format_version": 0}, 0), ({"format_version": 1}, 1), ({"format_version": 2}, 2), ({"format_version": 3}, 3), ({"format_version": 4}, 4), ({"format_version": 5}, 5), ({"format_version": 6}, 6)])
def test_save_format_version_parser(document, expected):
    assert parse_save_format_version(document) == expected


@pytest.mark.parametrize("value", [True, False, "1", 1.0, -1, 7, None, [], {}])
def test_save_format_version_parser_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="format_version"):
        parse_save_format_version({"format_version": value})


def test_canonical_save_document_always_contains_version_and_focus_without_side_effects():
    state = _state()
    focused = _focus(state)
    before = _fingerprint(state)
    document = make_save_document(state)
    assert document["format_version"] == CURRENT_SAVE_FORMAT_VERSION == 6
    assert document["player_position"] == {"x": 3, "y": 3}
    assert document["lod_runtime"] == []
    assert document["focused_object_id"] == "goblin:location/well"
    assert {k: document[k] for k in state.snapshot()} == state.snapshot()
    assert _fingerprint(state) == before
    state.clear_focused_object()
    assert make_save_document(state)["focused_object_id"] is None
    assert focused is not None


def test_version1_save_load_round_trip_restores_location_focus_and_rng(tmp_path):
    state = _state()
    focused = _focus(state)
    state.turn = 9
    state.hp = 11
    state.rng.next()
    saved = _fingerprint(state)
    controller = ConsoleController(state, str(tmp_path))
    controller._save("slot")

    state.transition_location("plaza")
    state.hp = 1
    state.turn = 99
    state.rng.next()
    assert controller._load("slot") is True
    assert state.snapshot() == saved["snapshot"]
    assert state.rng.state() == saved["rng"]
    assert state.focus_state.focused_object_id == focused
    assert state.location == "well"
    assert build_map(state.scenario, state.location).current == "well"


@pytest.mark.parametrize("explicit_version", [False, True])
def test_legacy_save_restores_base_state_and_clears_focus(tmp_path, explicit_version):
    source = _state()
    source.transition_location("well")
    source.turn = 4
    document = source.snapshot()
    if explicit_version:
        document["format_version"] = 0
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    live = _state()
    _focus(live, "plaza")
    controller = ConsoleController(live, str(tmp_path))
    assert controller._load("legacy") is True
    assert live.snapshot() == source.snapshot()
    assert live.focus_state.focused_object_id is None


def test_version1_missing_or_null_focus_clears_existing_focus(tmp_path):
    for name, include_field in (("missing", False), ("null", True)):
        source = _state()
        document = source.snapshot() | {"format_version": 1}
        if include_field:
            document["focused_object_id"] = None
        (tmp_path / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
        live = _state()
        _focus(live, "plaza")
        assert ConsoleController(live, str(tmp_path))._load(name) is True
        assert live.focus_state.focused_object_id is None


@pytest.mark.parametrize("focus", [
    True, 1, 1.0, "", " ", "broken", {}, [],
    "other:location/well", "goblin:location/missing", "goblin:location/plaza",
])
def test_invalid_version1_focus_is_atomic(tmp_path, focus):
    live = _state()
    _focus(live, "plaza")
    live.log.append({"t": 0, "type": "sentinel"})
    before = _fingerprint(live)
    document = live.snapshot() | {
        "format_version": 1,
        "location": "well",
        "focused_object_id": focus,
    }
    (tmp_path / "bad.json").write_text(json.dumps(document), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("bad") is False
    assert _fingerprint(live) == before


@pytest.mark.parametrize("mutation", [
    {"format_version": 2},
    {"scenario_id": "other"},
    {"rng_a": "bad"},
    {"rng_a": -1},
    {"hp": "bad"},
    {"location": "missing"},
    {"format_version": 0, "focused_object_id": None},
])
def test_invalid_save_document_is_atomic(tmp_path, mutation):
    live = _state()
    _focus(live, "plaza")
    before = _fingerprint(live)
    document = live.snapshot()
    document.update(mutation)
    (tmp_path / "invalid.json").write_text(json.dumps(document), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("invalid") is False
    assert _fingerprint(live) == before


def test_snapshot_schema_remains_focus_and_version_free():
    snapshot = _state().snapshot()
    assert not {"format_version", "focused_object_id", "focus", "focus_state", "world_objects", "lod_runtime"} & snapshot.keys()


def test_save_v2_round_trip_persists_only_lod_runtime_primitives(tmp_path):
    state = _state()
    well = _focus(state)
    state.lod_runtime = LodRuntimeState((ObjectLodProgress(
        well, ObjectAttentionState(3), ObjectLodState(2),
    ),))
    document = make_save_document(state)
    assert document["lod_runtime"] == [{
        "object_id": "goblin:location/well",
        "attention_level": 3,
        "unlocked_lod_cap": 2,
    }]
    assert not {"current_lod", "facts", "labels"} & document["lod_runtime"][0].keys()
    controller = ConsoleController(state, str(tmp_path))
    controller._save("lod")
    state.lod_runtime = LodRuntimeState()
    assert controller._load("lod") is True
    assert state.lod_runtime == LodRuntimeState((ObjectLodProgress(
        well, ObjectAttentionState(3), ObjectLodState(2),
    ),))


def test_save_v4_round_trip_persists_only_player_coordinates(tmp_path):
    state = _state()
    state.transition_location("well")
    state.player_position = PlayerPosition(2, 2)
    document = make_save_document(state)
    assert document["format_version"] == 6
    assert document["player_position"] == {"x": 2, "y": 2}
    assert set(document["player_position"]) == {"x", "y"}
    controller = ConsoleController(state, str(tmp_path))
    controller._save("position")
    state.player_position = PlayerPosition(1, 2)
    assert controller._load("position") is True
    assert state.player_position == PlayerPosition(2, 2)


@pytest.mark.parametrize("payload", [
    {}, [], {"x": 1}, {"x": 1, "y": 2, "z": 3},
    {"x": True, "y": 2}, {"x": 1.0, "y": 2}, {"x": "1", "y": 2},
    {"x": 0, "y": 0}, {"x": 3, "y": 2}, {"x": 7, "y": 2},
])
def test_invalid_save_v3_position_is_atomic(tmp_path, payload):
    live = _state()
    live.transition_location("well")
    before = _fingerprint(live)
    document = make_save_document(live)
    document["player_position"] = payload
    (tmp_path / "badposition.json").write_text(json.dumps(document), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("badposition") is False
    assert _fingerprint(live) == before


def test_non_null_position_requires_spatial_location(tmp_path):
    live = GameState(7, scenario=load_scenario("envoy"))
    before = _fingerprint(live)
    document = make_save_document(live)
    document["player_position"] = {"x": 1, "y": 2}
    (tmp_path / "badscene.json").write_text(json.dumps(document), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("badscene") is False
    assert _fingerprint(live) == before


def test_v3_null_position_migrates_to_catalog_spawn_and_v4_exit_is_rejected(tmp_path):
    live = _state()
    document = make_save_document(live)
    document["format_version"] = 3
    document.pop("story_spatial_active")
    document.pop("completed_village_actions")
    document["player_position"] = None
    (tmp_path / "legacy-null.json").write_text(
        json.dumps(document), encoding="utf-8",
    )
    assert ConsoleController(live, str(tmp_path))._load("legacy-null") is True
    assert live.player_position == PlayerPosition(3, 2)

    before = _fingerprint(live)
    invalid = make_save_document(live)
    invalid["player_position"] = {"x": 3, "y": 4}
    (tmp_path / "exit.json").write_text(json.dumps(invalid), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("exit") is False
    assert _fingerprint(live) == before


def test_save_v5_story_position_round_trip_and_trigger_rejection(tmp_path):
    live = _state()
    live.transition_node("forest", force=True)
    live.player_position = PlayerPosition(4, 2)
    document = make_save_document(live)
    assert document["format_version"] == 6
    assert document["story_spatial_active"] is True
    (tmp_path / "story.json").write_text(json.dumps(document), encoding="utf-8")
    live.transition_location("plaza")
    assert ConsoleController(live, str(tmp_path))._load("story") is True
    assert live.node == "forest" and live.player_position == PlayerPosition(4, 2)
    before = _fingerprint(live)
    document["player_position"] = {"x": 5, "y": 2}
    (tmp_path / "trigger.json").write_text(json.dumps(document), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("trigger") is False
    assert _fingerprint(live) == before


@pytest.mark.parametrize("bonus", [0, 1, 2, 3])
def test_save_v5_round_trips_applied_physical_damage_bonus(tmp_path, bonus):
    live = _state()
    live.effects = ([{"type": "damage_bonus", "kind": "physical", "value": bonus}]
                    if bonus else [])
    ConsoleController(live, str(tmp_path))._save("bonus")
    live.effects = [{"type": "damage_bonus", "kind": "physical", "value": 99}]
    assert ConsoleController(live, str(tmp_path))._load("bonus") is True
    from trpg_core.rules import effect_damage_bonus
    assert effect_damage_bonus(live, "physical") == bonus


@pytest.mark.parametrize("payload", [
    None, {}, [True],
    [{"object_id": "goblin:location/well", "attention_level": True, "unlocked_lod_cap": 1}],
    [{"object_id": "goblin:location/well", "attention_level": 1, "unlocked_lod_cap": 4}],
    [{"object_id": "other:location/well", "attention_level": 1, "unlocked_lod_cap": 1}],
])
def test_invalid_save_v2_lod_runtime_is_atomic(tmp_path, payload):
    live = _state()
    before = _fingerprint(live) | {"lod_runtime": live.lod_runtime}
    document = make_save_document(live)
    document["lod_runtime"] = payload
    (tmp_path / "badlod.json").write_text(json.dumps(document), encoding="utf-8")
    assert ConsoleController(live, str(tmp_path))._load("badlod") is False
    assert _fingerprint(live) | {"lod_runtime": live.lod_runtime} == before
