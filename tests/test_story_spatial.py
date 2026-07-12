import pytest

from trpg_core.input_actions import MovePlayerToPositionAction, StoryChoiceAction
from trpg_core.scenario_loader import load_scenario
from trpg_core.spatial import MovementStep, PlayerPosition, SceneCell
from trpg_core.story_spatial import (
    GOBLIN_STORY_SPATIAL_CATALOG, canonical_action_for_story_spatial_step,
    current_story_spatial_definition, story_entry_spawn_from_node,
    story_spatial_definition_for_node, story_trigger_at_cell,
    validate_story_spatial_catalog_topology,
)


def test_goblin_story_catalog_is_exact_and_topologically_valid():
    catalog = GOBLIN_STORY_SPATIAL_CATALOG
    assert tuple(d.node_id for d in catalog.definitions) == (
        "forest", "sneak_ok", "sneak_fail", "cave_hall",
    )
    validate_story_spatial_catalog_topology(catalog, load_scenario("goblin"))
    assert current_story_spatial_definition("envoy", "forest") is None
    assert story_spatial_definition_for_node(catalog, "missing") is None


def test_story_step_is_exactly_one_canonical_action():
    definition = current_story_spatial_definition("goblin", "forest")
    assert canonical_action_for_story_spatial_step(
        current_node_id="forest", current_position=PlayerPosition(3, 2),
        step=MovementStep(1, 0), definition=definition,
    ) == MovePlayerToPositionAction(PlayerPosition(4, 2))
    assert canonical_action_for_story_spatial_step(
        current_node_id="forest", current_position=PlayerPosition(4, 2),
        step=MovementStep(1, 0), definition=definition,
    ) == StoryChoiceAction("road")
    assert story_trigger_at_cell(definition, SceneCell(5, 2)).transition.choice_key == "road"


def test_story_entry_spawn_is_source_exact():
    definition = current_story_spatial_definition("goblin", "sneak_ok")
    assert story_entry_spawn_from_node(definition, "forest") == PlayerPosition(3, 2)
    assert story_entry_spawn_from_node(definition, "missing") is None


def test_story_runtime_entry_combat_boundary_and_direct_trigger_rejection():
    from trpg_core.session import GameState
    from trpg_core.spatial_actions import apply_player_movement
    state = GameState(7, scenario=load_scenario("goblin"))
    state.transition_node("forest", force=True)
    assert state.player_position == PlayerPosition(3, 2)
    state.player_position = PlayerPosition(4, 2)
    with pytest.raises(ValueError, match="trigger"):
        apply_player_movement(state, MovePlayerToPositionAction(PlayerPosition(5, 2)))
    state.transition_node("cave_entrance")
    assert state.player_position is None
    state.transition_node("cave_hall")
    assert state.player_position == PlayerPosition(3, 2)
