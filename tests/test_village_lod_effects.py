from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from trpg_core.input_actions import ExploreAction
from trpg_core.lod_content import lod_content_for_world_object, visible_facts_for_lod
from trpg_core.lod import ObjectAttentionState, ObjectLodState
from trpg_core.lod_actions import LodRuntimeState, ObjectLodProgress
from trpg_core.map import build_map
from trpg_core.rules import effect_hit_bonus, has_recon
from trpg_core.scenario_loader import load_scenario
from trpg_core.session import GameState, _apply_village_action, make_save_document, _validated_save_state
from trpg_core.presentation import build_render_snapshot
from trpg_core.village_lod_effects import (
    VILLAGE_LOD_EFFECT_SPECS, VillageEffectDelta,
    village_effect_for_lod, village_lod_effect_spec,
)
from trpg_core.world import WorldObjectId


CASES = (
    ("shrine", "shrine", ((0, 0, 0, 0, False), (0, 0, 1, 0, False),
                            (1, 0, 0, 0, False), (2, 0, 0, 0, False))),
    ("lookout", "scout", ((0, 0, 0, 0, False), (0, 1, 0, 0, False),
                            (0, 0, 0, 0, True), (0, 0, 1, 0, True))),
    ("herbhut", "herbs", ((0, 0, 0, 0, False), (0, 0, 0, 1, False),
                            (0, 0, 0, 2, False), (0, 0, 0, 3, False))),
    ("elderhouse", "elder", ((0, 0, 0, 0, False), (0, 0, 1, 0, False),
                               (0, 0, 2, 0, False), (0, 0, 3, 0, False))),
)


@pytest.mark.parametrize("scene,action,levels", CASES)
def test_closed_registry_has_exact_four_lod_mapping(scene, action, levels):
    object_id = WorldObjectId("goblin", f"location/{scene}")
    spec = village_lod_effect_spec(object_id, action)
    assert tuple(spec.effects_by_lod) == (0, 1, 2, 3)
    actual = tuple((value.global_hit_bonus, value.watcher_hit_bonus,
                    value.chief_hit_bonus, value.herbs_delta,
                    value.grants_recon)
                   for value in spec.effects_by_lod.values())
    assert actual == levels
    with pytest.raises(TypeError):
        spec.effects_by_lod[0] = VillageEffectDelta()


@pytest.mark.parametrize("bad", [True, 1.0, "1", None])
def test_registry_rejects_non_exact_lod_types(bad):
    spec = VILLAGE_LOD_EFFECT_SPECS[0]
    with pytest.raises(ValueError):
        village_effect_for_lod(spec.object_id, spec.action_key, bad)


def test_registry_rejects_unknown_and_mismatched_identity():
    with pytest.raises(ValueError, match="unknown"):
        village_lod_effect_spec(WorldObjectId("goblin", "location/missing"), "shrine")
    with pytest.raises(ValueError, match="do not match"):
        village_lod_effect_spec(WorldObjectId("goblin", "location/shrine"), "elder")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        VILLAGE_LOD_EFFECT_SPECS[0].action_key = "changed"


@pytest.mark.parametrize("scene,action,_levels", CASES)
def test_village_objects_have_cumulative_lod_content(scene, action, _levels):
    content = lod_content_for_world_object(
        WorldObjectId("goblin", f"location/{scene}"),
    )
    assert content.lod_spec.attention_thresholds == (0, 1, 3, 6)
    assert content.lod_spec.max_lod == 3
    visible = tuple(visible_facts_for_lod(content, lod).facts for lod in range(4))
    assert tuple(len(level) for level in visible) == (1, 2, 3, 4)
    assert all(set(left).issubset(right) for left, right in zip(visible, visible[1:]))


def _state_at(scene, action, lod):
    state = GameState(7, scenario=load_scenario("goblin"))
    state.location = scene
    state.player_position = state.spatial_definition_for_location(scene).player_spawn
    object_id = WorldObjectId("goblin", f"location/{scene}")
    attention = (0, 1, 3, 6)[lod]
    state.lod_runtime = LodRuntimeState((ObjectLodProgress(
        object_id, ObjectAttentionState(attention), ObjectLodState(3),
    ),))
    game_map = build_map(state.scenario, scene)
    before_rng = state.rng.state()
    picked = []
    _apply_village_action(state, game_map, picked, ExploreAction(action))
    return state, picked, before_rng


@pytest.mark.parametrize("scene,action,levels", CASES)
@pytest.mark.parametrize("lod", range(4))
def test_current_dispatch_applies_authoritative_lod_once(scene, action, levels, lod):
    state, picked, before_rng = _state_at(scene, action, lod)
    global_bonus, watcher, chief, herbs, recon = levels[lod]
    assert effect_hit_bonus(state, "goblin") == global_bonus
    assert effect_hit_bonus(state, "sentry") == global_bonus + watcher
    assert effect_hit_bonus(state, "chief") == global_bonus + chief
    assert state.herbs == herbs
    assert has_recon(state) is recon
    assert state.completed_village_actions == frozenset({action})
    assert picked == []
    assert state.rng.state() != before_rng
    with pytest.raises(ValueError, match="available"):
        _apply_village_action(state, build_map(state.scenario, scene), picked, ExploreAction(action))


def test_later_lod_change_does_not_upgrade_applied_effect():
    state, _, _ = _state_at("shrine", "shrine", 1)
    state.lod_runtime = LodRuntimeState((ObjectLodProgress(
        WorldObjectId("goblin", "location/shrine"),
        ObjectAttentionState(6), ObjectLodState(3),
    ),))
    assert effect_hit_bonus(state, "chief") == 1
    assert effect_hit_bonus(state, "goblin") == 0


def test_save_v6_round_trips_zero_effect_completion_and_effects():
    state, _, _ = _state_at("elderhouse", "elder", 0)
    document = make_save_document(state)
    candidate, _ = _validated_save_state(document, state.scenario)
    assert candidate.completed_village_actions == frozenset({"elder"})
    assert candidate.effects == []


def test_save_v6_rejects_unknown_duplicate_and_contradictory_completion():
    state = GameState(7, scenario=load_scenario("goblin"))
    for values in (["missing"], ["elder", "elder"]):
        document = make_save_document(state)
        document["completed_village_actions"] = values
        with pytest.raises(ValueError):
            _validated_save_state(document, state.scenario)
    document = make_save_document(state)
    document["completed_village_actions"] = ["elder"]
    with pytest.raises(ValueError, match="contradict"):
        _validated_save_state(document, state.scenario)


def test_v5_migration_uses_exact_legacy_label_after_herb_consumption():
    state = GameState(7, scenario=load_scenario("goblin"))
    state.buff_labels = ["薬草の女を訪ねる"]
    state.herbs = 0
    document = make_save_document(state)
    document["format_version"] = 5
    document.pop("completed_village_actions")
    candidate, _ = _validated_save_state(document, state.scenario)
    assert candidate.completed_village_actions == frozenset({"herbs"})


def test_presentation_exposes_only_typed_active_status_totals():
    state = GameState(7, scenario=load_scenario("goblin"))
    state.effects = [
        {"type": "hit_bonus", "value": 1},
        {"type": "hit_bonus", "target_enemy": "sentry", "value": 2},
        {"type": "hit_bonus", "target_enemy": "chief", "value": 3},
        {"type": "recon"},
    ]
    player = build_render_snapshot(state).player
    assert (player.global_hit_bonus, player.watcher_hit_bonus,
            player.chief_hit_bonus, player.recon_active) == (1, 2, 3, True)
    assert not hasattr(player, "effects")
