from __future__ import annotations

import copy
import os

import pytest

from trpg_core.record import fixture_from_inputs
from trpg_core.replay import (
    FixtureController, assert_focus_trace_matches, assert_lod_trace_matches,
    expected_focus_trace, expected_lod_trace, load_fixture, replay_fixture,
)
from trpg_core.world import WorldObjectId
from trpg_core.scenario_loader import load_scenario


LEGACY_INPUTS = [
    "explore:rapport",
    "explore:guard",
    "choice:双方の言い分を見立てて説く【mag 判定 / 目標 8：弁舌】",
    "choice:上流に理ありと裁く（片方に加担）",
]


def test_new_fixture_is_v2_and_canonicalizes_choice_labels():
    fixture = fixture_from_inputs("envoy", 0, LEGACY_INPUTS, respawn=True)
    assert fixture["format_version"] == 2
    assert fixture["scenario"] == "envoy"
    assert fixture["seed"] == 0
    assert "explore:rapport" in fixture["inputs"]
    assert "explore:guard" in fixture["inputs"]
    assert "choice:hear" in fixture["inputs"]
    assert "choice:side_up" in fixture["inputs"]
    assert "depart" in fixture["inputs"]
    assert any(token.startswith("move-to:envoy:location/") for token in fixture["inputs"])
    assert all("言い分" not in token and "上流" not in token for token in fixture["inputs"])
    ok, actual, diff = replay_fixture(fixture)
    assert ok, diff
    assert actual == fixture["expected_log"]
    assert fixture["respawn"] is True


@pytest.mark.parametrize("value", [
    "hea", "双方の言い分を見立てて説く【mag 判定 / 目標 8：弁舌】", "双方の言い分", "missing",
])
def test_v1_choice_requires_exact_canonical_key(value):
    controller = FixtureController([f"choice:{value}"], load_scenario("envoy"), format_version=1)
    with pytest.raises(ValueError, match="choice key"):
        controller.choice("table", ())


def test_v1_choice_exact_key_selects_the_intended_option():
    controller = FixtureController(["choice:overawe"], load_scenario("envoy"), format_version=1)
    assert controller.choice("table", ()) == "overawe"


def test_v0_keeps_exact_and_unique_partial_label_resolution():
    scenario = load_scenario("envoy")
    exact = FixtureController([f"choice:{LEGACY_INPUTS[2][7:]}"], scenario, format_version=0)
    partial = FixtureController(["choice:双方の言い分"], scenario, format_version=0)
    assert exact.choice("table", ()) == "hear"
    assert partial.choice("table", ()) == "hear"


def test_unconsumed_event_check_is_non_destructive_and_diagnostic():
    controller = FixtureController(["combat:attack", "unknown:tail"], load_scenario("goblin"))
    before = controller.remaining_events()
    with pytest.raises(ValueError, match=r"remaining=2.*combat:attack"):
        controller.assert_all_events_consumed()
    assert controller.remaining_events() == before


@pytest.mark.parametrize("tail", ["combat:attack", "unknown:tail"])
def test_programmatic_replay_rejects_trailing_events(tail):
    fixture = fixture_from_inputs("envoy", 0, LEGACY_INPUTS, respawn=True)
    bad = copy.deepcopy(fixture)
    bad["inputs"].append(tail)
    with pytest.raises(ValueError, match=r"remaining=1"):
        replay_fixture(bad)


@pytest.mark.parametrize("value", ["bad", True, 1, 1.0, {}, [[]], [""], ["not-an-id"]])
def test_expected_focus_trace_rejects_malformed_schema(value):
    fixture = {"format_version": 1, "expected_focus_trace": value}
    with pytest.raises(ValueError, match="expected_focus_trace|world object ID|value"):
        expected_focus_trace(fixture, format_version=1)


def test_expected_focus_trace_version_and_optional_contract():
    assert expected_focus_trace({"format_version": 1}, format_version=1) is None
    assert expected_focus_trace(
        {"format_version": 1, "expected_focus_trace": []}, format_version=1,
    ) == ()
    parsed = expected_focus_trace(
        {"format_version": 1, "expected_focus_trace": ["goblin:location/well", None]},
        format_version=1,
    )
    assert parsed == (WorldObjectId("goblin", "location/well"), None)
    with pytest.raises(ValueError, match="only for format_version 1"):
        expected_focus_trace({"expected_focus_trace": []}, format_version=0)


@pytest.mark.parametrize("expected,actual", [
    ((WorldObjectId("goblin", "location/well"),), (None,)),
    ((None,), ()),
    ((), (None,)),
    ((None, WorldObjectId("goblin", "location/well")),
     (WorldObjectId("goblin", "location/well"), None)),
])
def test_focus_trace_comparison_is_exact_and_diagnostic(expected, actual):
    with pytest.raises(ValueError, match=r"expected_focus_trace mismatch: .*expected_count=.*actual_count=.*index=.*expected=.*actual="):
        assert_focus_trace_matches(expected, actual)


def test_focus_v1_acceptance_fixture_replays_deterministically():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "focus_play_v1.json")
    fixture = load_fixture(path)
    assert fixture["format_version"] == 1
    assert fixture["expected_focus_trace"] == ["envoy:location/teahouse", None]
    for forbidden in ("focus next", "focus prev"):
        assert all(forbidden not in token for token in fixture["inputs"])
    first = replay_fixture(fixture, mode="full")
    second = replay_fixture(fixture, mode="full")
    assert first == second
    assert first[0] and first[1] == fixture["expected_log"]


def test_focus_v1_trace_mismatch_fails_after_log_match():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "focus_play_v1.json")
    fixture = copy.deepcopy(load_fixture(path))
    fixture["expected_focus_trace"] = [None, "envoy:location/teahouse"]
    with pytest.raises(ValueError, match="expected_focus_trace mismatch"):
        replay_fixture(fixture, mode="full")


def test_focus_v1_field_omission_preserves_existing_replay_behavior():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "focus_play_v1.json")
    fixture = copy.deepcopy(load_fixture(path))
    del fixture["expected_focus_trace"]
    ok, actual, diff = replay_fixture(fixture, mode="full")
    assert ok and diff is None and actual == fixture["expected_log"]


def test_expected_lod_trace_v2_schema_and_exact_comparison():
    fixture = {"format_version": 2, "expected_lod_trace": [[{
        "object_id": "goblin:location/well",
        "attention_level": 6,
        "unlocked_lod_cap": 3,
        "current_lod": 3,
    }]]}
    parsed = expected_lod_trace(fixture, format_version=2)
    assert parsed == ((('goblin:location/well', 6, 3, 3),),)
    assert_lod_trace_matches(parsed, parsed)
    with pytest.raises(ValueError, match="expected_lod_trace mismatch"):
        assert_lod_trace_matches(parsed, ())


@pytest.mark.parametrize("value", [
    {}, [True], [[{"object_id": "goblin:location/well"}]],
    [[{"object_id": "goblin:location/well", "attention_level": True,
       "unlocked_lod_cap": 3, "current_lod": 1}]],
])
def test_expected_lod_trace_rejects_malformed_schema(value):
    with pytest.raises(ValueError, match="expected_lod_trace"):
        expected_lod_trace(
            {"format_version": 2, "expected_lod_trace": value}, format_version=2,
        )


def test_lod_v2_trace_mismatch_fails_after_log_match():
    path = os.path.join(os.path.dirname(__file__), "fixtures", "lod_play_v2.json")
    fixture = copy.deepcopy(load_fixture(path))
    fixture["expected_lod_trace"][-1][0]["current_lod"] = 2
    with pytest.raises(ValueError, match="expected_lod_trace mismatch"):
        replay_fixture(fixture, mode="full")
