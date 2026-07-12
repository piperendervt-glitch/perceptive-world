import pytest

from trpg_core.presentation import SceneSpatialView, SpatialCellView, SpatialObjectView
from trpg_core.two_d import (
    build_side_panel_layout, build_two_d_layout, controls_text_for_phase,
    pixel_rect_for_cell,
    spatial_object_at_pixel,
)
from trpg_core.world import WorldObjectId


def _scene(focus=True):
    return SceneSpatialView(
        7, 5, (SpatialCellView(1, 1),), (), SpatialCellView(1, 2),
        (SpatialObjectView(WorldObjectId("goblin", "location/well"), "古井戸",
                           SpatialCellView(3, 2), True, focus),),
    )


def test_layout_is_left_map_right_panel_bottom_controls_and_deterministic():
    one = build_two_d_layout(window_width=1000, window_height=700, scene_width=7, scene_height=5)
    two = build_two_d_layout(window_width=1000, window_height=700, scene_width=7, scene_height=5)
    assert one == two and one.cell_size > 0
    assert one.map_rect.left == 0
    assert one.side_panel_rect.left == one.map_rect.width
    assert one.controls_rect.top == one.map_rect.height
    assert one.map_rect.width + one.side_panel_rect.width == one.window_width


def test_side_panel_sections_remain_ordered_with_four_exits_and_long_feedback():
    layout = build_side_panel_layout(
        panel_height=586, exit_count=4, scene_action_count=2,
        focus_action_count=3, feedback="長いfeedback" * 30,
    )
    assert (layout.status_top < layout.info_top < layout.exits_top
            < layout.scene_actions_top < layout.focus_actions_top)
    assert layout.focus_actions_top + 3 * (layout.button_height + 4) <= 598


def test_controls_copy_is_phase_specific():
    assert "WASD" in controls_text_for_phase("village")
    assert "WASD" in controls_text_for_phase("story")
    assert "Focus" not in controls_text_for_phase("combat")
    assert "Q" in controls_text_for_phase("ending")


@pytest.mark.parametrize("kwargs", [
    {"window_width": 0, "window_height": 700, "scene_width": 7, "scene_height": 5},
    {"window_width": 1000, "window_height": True, "scene_width": 7, "scene_height": 5},
    {"window_width": 5, "window_height": 5, "scene_width": 7, "scene_height": 5},
])
def test_layout_rejects_invalid_sizes(kwargs):
    with pytest.raises(ValueError): build_two_d_layout(**kwargs)


def test_cell_rect_and_hit_test_use_exact_half_open_cells():
    layout = build_two_d_layout(window_width=1000, window_height=700, scene_width=7, scene_height=5)
    rect = pixel_rect_for_cell(layout, SpatialCellView(3, 2))
    object_id = spatial_object_at_pixel(_scene(), layout,
                                        x=rect.left + rect.width // 2,
                                        y=rect.top + rect.height // 2)
    assert object_id == WorldObjectId("goblin", "location/well")
    assert spatial_object_at_pixel(_scene(False), layout, x=rect.left, y=rect.top) is None
    assert spatial_object_at_pixel(_scene(), layout, x=layout.side_panel_rect.left, y=1) is None
    player = pixel_rect_for_cell(layout, SpatialCellView(1, 2))
    assert spatial_object_at_pixel(_scene(), layout, x=player.left, y=player.top) is None


def test_out_of_bounds_cell_is_rejected():
    layout = build_two_d_layout(window_width=1000, window_height=700, scene_width=7, scene_height=5)
    with pytest.raises(ValueError): pixel_rect_for_cell(layout, SpatialCellView(7, 0))
