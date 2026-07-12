import dataclasses
import sys

import pytest

from trpg_core.spatial import (
    MovementStep,
    ObjectPosition,
    PlayerPosition,
    SceneBounds,
    SceneCell,
    SceneSpatialSpec,
    SpatialObjectPlacement,
    can_player_occupy,
    is_blocked_cell,
    is_walkable_cell,
    object_placement_for_world_object,
    player_position_after_step,
    scene_bounds_contains,
)
from trpg_core.world import WorldObjectId


def _placement(local_id, x, y, blocks):
    return SpatialObjectPlacement(
        WorldObjectId("test", local_id), ObjectPosition(x, y), blocks,
    )


def _spec():
    return SceneSpatialSpec(
        "well",
        SceneBounds(5, 4),
        tuple(SceneCell(x, y) for x, y in (
            (1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2),
        )),
        (_placement("location/well", 3, 1, True),
         _placement("object/marker", 1, 2, False)),
    )


@pytest.mark.parametrize("model", [SceneCell, PlayerPosition, ObjectPosition])
def test_coordinate_models_are_strict_frozen_hashable_values(model):
    value = model(-1, 2)
    assert value == model(-1, 2)
    assert hash(value) == hash(model(-1, 2))
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.x = 0
    for invalid in (True, 1.0, "1", None):
        with pytest.raises(ValueError):
            model(invalid, 0)
        with pytest.raises(ValueError):
            model(0, invalid)


def test_position_models_do_not_conflate_other_domain_state():
    assert {field.name for field in dataclasses.fields(PlayerPosition)} == {"x", "y"}
    assert {field.name for field in dataclasses.fields(ObjectPosition)} == {"x", "y"}


@pytest.mark.parametrize("field,value", [
    ("width", 0), ("height", 0), ("width", -1), ("height", -1),
    ("width", True), ("height", False), ("width", 1.0), ("height", "2"),
])
def test_bounds_requires_strict_positive_dimensions(field, value):
    values = {"width": 5, "height": 4}
    values[field] = value
    with pytest.raises(ValueError):
        SceneBounds(**values)


def test_bounds_contains_uses_zero_origin_and_exclusive_edges():
    bounds = SceneBounds(5, 4)
    assert scene_bounds_contains(bounds, SceneCell(0, 0))
    assert scene_bounds_contains(bounds, SceneCell(4, 3))
    for cell in (SceneCell(-1, 0), SceneCell(0, -1), SceneCell(5, 0), SceneCell(0, 4)):
        assert not scene_bounds_contains(bounds, cell)


@pytest.mark.parametrize("step", [(0, -1), (1, 0), (0, 1), (-1, 0)])
def test_movement_step_accepts_only_cardinal_unit_steps(step):
    assert MovementStep(*step) == MovementStep(*step)


@pytest.mark.parametrize("step", [(0, 0), (1, 1), (2, 0), (0, -2), (True, 0)])
def test_movement_step_rejects_invalid_steps(step):
    with pytest.raises(ValueError):
        MovementStep(*step)


def test_candidate_position_is_pure_arithmetic_without_collision():
    position = PlayerPosition(1, 1)
    step = MovementStep(1, 0)
    assert player_position_after_step(position, step) == PlayerPosition(2, 1)
    assert position == PlayerPosition(1, 1)
    assert step == MovementStep(1, 0)


def test_placement_is_strict_frozen_and_has_only_physical_fields():
    placement = _placement("location/well", 3, 1, True)
    assert {field.name for field in dataclasses.fields(placement)} == {
        "object_id", "position", "blocks_movement",
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        placement.blocks_movement = False
    for args in (("id", ObjectPosition(1, 1), True),
                 (WorldObjectId("test", "x"), SceneCell(1, 1), True),
                 (WorldObjectId("test", "x"), ObjectPosition(1, 1), 1)):
        with pytest.raises(ValueError):
            SpatialObjectPlacement(*args)


def test_scene_spec_preserves_tuple_order_and_is_frozen():
    spec = _spec()
    assert spec.walkable_cells[0] == SceneCell(1, 1)
    assert [p.object_id.local_id for p in spec.object_placements] == [
        "location/well", "object/marker",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.scene_id = "other"


@pytest.mark.parametrize("field,value", [
    ("scene_id", None), ("scene_id", ""), ("bounds", (5, 4)),
    ("walkable_cells", [SceneCell(1, 1)]), ("object_placements", []),
    ("walkable_cells", ()), ("walkable_cells", ("1,1",)),
    ("object_placements", ("well",)),
])
def test_scene_spec_rejects_invalid_aggregate_fields(field, value):
    values = dataclasses.asdict(_spec())
    values = {
        "scene_id": _spec().scene_id, "bounds": _spec().bounds,
        "walkable_cells": _spec().walkable_cells,
        "object_placements": _spec().object_placements,
    }
    values[field] = value
    with pytest.raises(ValueError):
        SceneSpatialSpec(**values)


def test_scene_spec_rejects_duplicates_and_out_of_bounds_values():
    base = _spec()
    invalid = (
        (base.walkable_cells + (base.walkable_cells[0],), base.object_placements),
        (base.walkable_cells, base.object_placements + (
            _placement("location/well", 4, 3, False),)),
        (base.walkable_cells, base.object_placements + (
            _placement("object/other", 3, 1, False),)),
        (base.walkable_cells + (SceneCell(5, 1),), base.object_placements),
        (base.walkable_cells, base.object_placements + (
            _placement("object/outside", 5, 1, False),)),
    )
    for walkable, placements in invalid:
        with pytest.raises(ValueError):
            SceneSpatialSpec("well", base.bounds, walkable, placements)


def test_exact_object_query_has_no_local_or_prefix_fallback():
    spec = _spec()
    well = WorldObjectId("test", "location/well")
    assert object_placement_for_world_object(spec, well) == spec.object_placements[0]
    for object_id in (WorldObjectId("other", "location/well"),
                      WorldObjectId("test", "location/wel"),
                      WorldObjectId("test", "location/well/deeper")):
        assert object_placement_for_world_object(spec, object_id) is None


def test_walkability_blocking_and_occupancy_synthetic_slice():
    spec = _spec()
    assert is_walkable_cell(spec, SceneCell(2, 1))
    assert not is_walkable_cell(spec, SceneCell(0, 0))
    assert not is_walkable_cell(spec, SceneCell(5, 1))
    assert can_player_occupy(spec, PlayerPosition(1, 1))
    assert can_player_occupy(spec, PlayerPosition(2, 1))
    assert is_blocked_cell(spec, SceneCell(3, 1))
    assert not can_player_occupy(spec, PlayerPosition(3, 1))
    assert not is_blocked_cell(spec, SceneCell(1, 2))
    assert can_player_occupy(spec, PlayerPosition(1, 2))
    assert not can_player_occupy(spec, PlayerPosition(5, 1))


def test_spatial_module_has_no_runtime_or_presentation_dependencies():
    import trpg_core.spatial as spatial

    source_names = set(spatial.__dict__)
    assert "FocusState" not in source_names
    assert "GameState" not in source_names
    assert "trpg_core.presentation" not in sys.modules or not hasattr(spatial, "presentation")
    assert "trpg_core.tui" not in sys.modules or not hasattr(spatial, "tui")
