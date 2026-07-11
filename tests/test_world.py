"""WorldObject IDとFocusStateのpure modelテスト。"""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields

import pytest

import trpg_core.world as world
from trpg_core.map import GameMap, Location, build_map
from trpg_core.scenario_loader import load_scenario
from trpg_core.world import (
    FocusState,
    WorldObjectId,
    WorldObjectSpec,
    clear_focus,
    build_map_location_world_object_specs,
    location_world_object_id,
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


def test_location_world_object_id_is_stable_and_namespaced():
    one = location_world_object_id("goblin", "well")
    two = location_world_object_id("goblin", "well")
    assert one == two == WorldObjectId("goblin", "location/well")
    assert serialize_world_object_id(one) == "goblin:location/well"
    assert location_world_object_id("ruins", "well") != one
    assert location_world_object_id("goblin", "shrine") != one


@pytest.mark.parametrize(
    ("scenario_id", "location_id"),
    [
        ("", "well"),
        ("goblin", ""),
        ("goblin", " well"),
        ("goblin", "well "),
        ("goblin", "/well"),
        ("goblin", "well/"),
        ("goblin", "old//well"),
    ],
)
def test_location_world_object_id_rejects_invalid_values(scenario_id, location_id):
    with pytest.raises(ValueError):
        location_world_object_id(scenario_id, location_id)


def _game_map(location_items, current):
    return GameMap(dict(location_items), current)


def test_map_query_builds_one_immutable_location_spec():
    game_map = _game_map([
        ("well", Location("well", "古井戸", {"south": "plaza"})),
    ], "well")
    specs = build_map_location_world_object_specs("goblin", game_map)
    assert specs == (
        WorldObjectSpec(
            WorldObjectId("goblin", "location/well"),
            "location", "古井戸", "well",
        ),
    )


def test_map_query_includes_every_location_in_location_id_order():
    game_map = _game_map([
        ("well", Location("well", "古井戸")),
        ("plaza", Location("plaza", "村の広場")),
        ("shrine", Location("shrine", "古い祠")),
    ], "plaza")
    specs = build_map_location_world_object_specs("goblin", game_map)
    assert [spec.scene_id for spec in specs] == ["plaza", "shrine", "well"]
    assert all(spec.kind == "location" for spec in specs)
    assert [spec.label for spec in specs] == ["村の広場", "古い祠", "古井戸"]
    assert len({spec.object_id for spec in specs}) == 3


def test_map_query_order_does_not_depend_on_dict_insertion_order():
    locations = [
        ("well", Location("well", "古井戸")),
        ("plaza", Location("plaza", "村の広場")),
        ("shrine", Location("shrine", "古い祠")),
    ]
    forward = _game_map(locations, "well")
    reverse = _game_map(reversed(locations), "well")
    assert build_map_location_world_object_specs("goblin", forward) == (
        build_map_location_world_object_specs("goblin", reverse)
    )


def test_map_query_is_independent_of_current_and_does_not_change_it():
    locations = [
        ("well", Location("well", "古井戸")),
        ("plaza", Location("plaza", "村の広場")),
    ]
    at_well = _game_map(locations, "well")
    at_plaza = _game_map(locations, "plaza")
    expected = build_map_location_world_object_specs("goblin", at_well)
    assert build_map_location_world_object_specs("goblin", at_plaza) == expected
    assert at_well.current == "well"
    assert at_plaza.current == "plaza"


def test_map_query_is_independent_of_exits_and_does_not_change_input():
    first = Location("well", "古井戸", {"south": "plaza", "north": "lookout"})
    second = Location("well", "古井戸", {"north": "lookout", "south": "plaza"})
    first_map = _game_map([("well", first)], "well")
    second_map = _game_map([("well", second)], "well")
    before = (first_map.current, tuple(first_map.locations), first.name, dict(first.exits))
    assert build_map_location_world_object_specs("goblin", first_map) == (
        build_map_location_world_object_specs("goblin", second_map)
    )
    assert (first_map.current, tuple(first_map.locations), first.name, first.exits) == before


def test_map_query_label_change_does_not_change_identity():
    japanese = _game_map([("well", Location("well", "古井戸"))], "well")
    english = _game_map([("well", Location("well", "Old Well"))], "well")
    before = build_map_location_world_object_specs("goblin", japanese)[0]
    after = build_map_location_world_object_specs("goblin", english)[0]
    assert before.object_id == after.object_id
    assert before.scene_id == after.scene_id == "well"
    assert before.kind == after.kind == "location"
    assert before.label != after.label


def test_goblin_well_uses_existing_map_data():
    scenario = load_scenario("goblin")
    specs = build_map_location_world_object_specs(scenario.id, build_map(scenario))
    well = next(spec for spec in specs if spec.scene_id == "well")
    assert serialize_world_object_id(well.object_id) == "goblin:location/well"
    assert well.kind == "location"
    assert well.label == "古井戸"


def test_map_query_does_not_change_focus_state():
    focused = FocusState(_id())
    game_map = _game_map([("well", Location("well", "古井戸"))], "well")
    build_map_location_world_object_specs("goblin", game_map)
    assert focused == FocusState(_id())


def test_map_query_uses_domain_map_not_presentation_map_view():
    source = inspect.getsource(world)
    assert "from .map import GameMap" in source
    assert "MapView" not in source
    assert "scenario_loader" not in source
