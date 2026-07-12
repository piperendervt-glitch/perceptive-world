import copy

import pytest

from trpg_core.input_actions import ExploreAction
from trpg_core.lod import ObjectAttentionState, ObjectLodState
from trpg_core.lod_actions import LodRuntimeState, ObjectLodProgress
from trpg_core.map import build_map
from trpg_core.rules import effect_damage_bonus
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import GameState, _apply_village_action
from trpg_core.well_effects import (
    WellEffectTier, well_effect_tier_for_lod, well_physical_damage_bonus_for_lod,
)
from trpg_core.world import WorldObjectId


@pytest.mark.parametrize("lod,tier", [
    (0, WellEffectTier.NONE), (1, WellEffectTier.MINOR),
    (2, WellEffectTier.NORMAL), (3, WellEffectTier.MAXIMUM),
])
def test_pure_well_effect_mapping(lod, tier):
    assert well_effect_tier_for_lod(lod) is tier
    assert well_physical_damage_bonus_for_lod(lod) == lod


@pytest.mark.parametrize("value", [True, False, -1, 4, 1.0, "1", None])
def test_pure_well_effect_mapping_rejects_invalid_lod(value):
    with pytest.raises(ValueError): well_effect_tier_for_lod(value)
    with pytest.raises(ValueError): well_physical_damage_bonus_for_lod(value)


@pytest.mark.parametrize("attention,cap,bonus", [(0,3,0),(1,3,1),(3,3,2),(6,3,3),(6,1,1)])
def test_well_explore_applies_authoritative_lod_once(attention, cap, bonus):
    state = GameState(7, scenario=load_scenario("goblin")); state.transition_location("well")
    well = WorldObjectId("goblin", "location/well")
    state.lod_runtime = LodRuntimeState((ObjectLodProgress(
        well, ObjectAttentionState(attention), ObjectLodState(cap),
    ),))
    game_map = build_map(state.scenario, "well"); picked = []
    rng = state.rng.state(); position = state.player_position; runtime = state.lod_runtime
    assert not _apply_village_action(state, game_map, picked, ExploreAction("well"))
    assert effect_damage_bonus(state, "physical") == bonus
    assert picked == ["well"] and state.player_position == position and state.lod_runtime == runtime
    assert state.rng.state() != rng  # existing explore consumes exactly one d6
    before = copy.deepcopy(state.effects)
    state.lod_runtime = LodRuntimeState((ObjectLodProgress(
        well, ObjectAttentionState(6), ObjectLodState(3),
    ),))
    with pytest.raises(ValueError):
        _apply_village_action(state, game_map, picked, ExploreAction("well"))
    assert state.effects == before


def test_legacy_profile_keeps_fixed_plus_two():
    state = GameState(7, scenario=load_scenario("goblin")); state.transition_location("well")
    _apply_village_action(state, build_map(state.scenario, "well"), [], ExploreAction("well"), well_effect_profile="legacy")
    assert effect_damage_bonus(state, "physical") == 2
