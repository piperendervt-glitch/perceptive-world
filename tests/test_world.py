"""WorldObject IDとFocusStateのpure modelテスト。"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields

import pytest

import trpg_core.world as world
from trpg_core.world import (
    FocusState,
    WorldObjectId,
    WorldObjectSpec,
    clear_focus,
    parse_world_object_id,
    serialize_world_object_id,
    set_focus,
    validate_world_object_specs,
)


def _id(scenario="goblin", local="location/well"):
    return WorldObjectId(scenario, local)


def _spec(object_id=None, *, kind="location", label="古井戸", scene_id="well"):
    return WorldObjectSpec(object_id or _id(), kind, label, scene_id)


@pytest.mark.parametrize("factory", [_id, _spec, FocusState])
def test_models_are_frozen(factory):
    value = factory()
    with pytest.raises(FrozenInstanceError):
        setattr(value, fields(value)[0].name, None)


def test_world_object_id_is_hashable_and_namespaced_by_scenario():
    goblin = _id()
    ruins = _id("ruins")
    assert {goblin: "well", ruins: "other"}[goblin] == "well"
    assert goblin != ruins


def test_world_object_id_serialization_round_trips():
    object_id = _id()
    assert serialize_world_object_id(object_id) == "goblin:location/well"
    assert parse_world_object_id("goblin:location/well") == object_id
    assert parse_world_object_id(serialize_world_object_id(object_id)) == object_id
    assert serialize_world_object_id(parse_world_object_id("goblin:location/well")) == (
        "goblin:location/well"
    )


@pytest.mark.parametrize(
    ("scenario_id", "local_id"),
    [
        ("", "location/well"),
        ("goblin", ""),
        (" goblin", "location/well"),
        ("goblin ", "location/well"),
        ("goblin", " location/well"),
        ("goblin", "location/well "),
        ("goblin:chapter", "location/well"),
        ("goblin", "/location/well"),
        ("goblin", "location/well/"),
        ("goblin", "location//well"),
    ],
)
def test_world_object_id_rejects_invalid_values(scenario_id, local_id):
    with pytest.raises(ValueError):
        WorldObjectId(scenario_id, local_id)


@pytest.mark.parametrize("value", ["", "goblin", ":location/well", "goblin:"])
def test_parse_rejects_incomplete_serialized_ids(value):
    with pytest.raises(ValueError):
        parse_world_object_id(value)


def test_validation_is_not_unnecessarily_restrictive():
    assert WorldObjectId("scenario-v1", "location/old_well-2")
    assert parse_world_object_id("scenario-v1:location/old_well-2")


def test_world_object_spec_keeps_identity_separate_from_label():
    object_id = _id()
    original = _spec(object_id, label="古井戸")
    renamed = _spec(object_id, label="Old Well")
    assert original.object_id == renamed.object_id == object_id
    assert original.scene_id == "well"


@pytest.mark.parametrize(
    ("kind", "label"),
    [("", "古井戸"), (" location", "古井戸"), ("location ", "古井戸"),
     ("location", ""), ("location", " 古井戸"), ("location", "古井戸 ")],
)
def test_world_object_spec_rejects_invalid_kind_and_label(kind, label):
    with pytest.raises(ValueError):
        _spec(kind=kind, label=label)


def test_validate_specs_copies_to_tuple_preserves_order_and_input():
    source = [_spec(), _spec(_id("ruins"), label="別の井戸")]
    before = list(source)
    result = validate_world_object_specs(source)
    assert result == tuple(source)
    assert source == before


def test_validate_specs_accepts_empty_and_scenario_namespaced_ids():
    assert validate_world_object_specs([]) == ()
    assert len(validate_world_object_specs([
        _spec(_id("goblin")), _spec(_id("ruins"), label="別の井戸"),
    ])) == 2


@pytest.mark.parametrize("change", ["label", "kind"])
def test_validate_specs_rejects_duplicate_id_regardless_of_other_fields(change):
    first = _spec()
    kwargs = {change: "別値"}
    duplicate = _spec(**kwargs)
    with pytest.raises(ValueError):
        validate_world_object_specs([first, duplicate])


def test_focus_state_sets_changes_repeats_and_clears_without_mutation():
    well = _id()
    shrine = _id(local="location/shrine")
    initial = FocusState()
    focused = set_focus(initial, well, focusable_object_ids=[well, shrine])
    changed = set_focus(focused, shrine, focusable_object_ids=(well, shrine))
    repeated = set_focus(changed, shrine, focusable_object_ids={well, shrine})
    cleared = clear_focus(changed)
    assert initial.focused_object_id is None
    assert focused.focused_object_id == well
    assert changed.focused_object_id == shrine
    assert repeated is changed
    assert cleared == FocusState()
    assert clear_focus(cleared) is cleared


@pytest.mark.parametrize("reason", ["missing", "scene-outside", "hidden", "disabled"])
def test_set_focus_rejects_any_id_outside_authoritative_collection(reason):
    current = _id(local="location/shrine")
    rejected = _id(local=f"object/{reason}")
    state = FocusState(current)
    focusable = [current]
    before = list(focusable)
    with pytest.raises(ValueError):
        set_focus(state, rejected, focusable_object_ids=focusable)
    assert state == FocusState(current)
    assert focusable == before


def test_focus_update_is_deterministic_for_equal_inputs():
    object_id = _id()
    one = set_focus(FocusState(), object_id, focusable_object_ids=(object_id,))
    two = set_focus(FocusState(), object_id, focusable_object_ids=(object_id,))
    assert one == two


def test_world_model_stays_separate_from_ui_and_existing_engine_modules():
    assert {field.name for field in fields(FocusState)} == {"focused_object_id"}
    source = inspect.getsource(world)
    for module in (
        "session", "input_actions", "presentation", "tui", "record", "replay",
        "scenario_loader", "combat", "village",
    ):
        assert f"from .{module}" not in source
        assert f"import trpg_core.{module}" not in source
