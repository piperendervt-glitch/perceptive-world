from __future__ import annotations

import copy

import pytest

from trpg_core.record import fixture_from_inputs
from trpg_core.replay import FixtureController, replay_fixture
from trpg_core.scenario_loader import load_scenario


LEGACY_INPUTS = [
    "explore:rapport",
    "explore:guard",
    "choice:双方の言い分を見立てて説く【mag 判定 / 目標 8：弁舌】",
    "choice:上流に理ありと裁く（片方に加担）",
]


def test_new_fixture_is_v1_and_canonicalizes_choice_labels():
    fixture = fixture_from_inputs("envoy", 0, LEGACY_INPUTS, respawn=True)
    assert fixture["format_version"] == 1
    assert fixture["scenario"] == "envoy"
    assert fixture["seed"] == 0
    assert fixture["inputs"] == [
        "explore:rapport", "explore:guard", "choice:hear", "choice:side_up",
    ]
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
