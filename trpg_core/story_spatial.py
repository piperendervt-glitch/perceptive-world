"""Pure spatial contracts for canonical non-combat story nodes."""

from dataclasses import dataclass

from .input_actions import MovePlayerToPositionAction, StoryChoiceAction
from .spatial import (
    MovementStep, PlayerPosition, SceneBounds, SceneCell, SceneSpatialSpec,
    can_player_occupy, player_position_after_step,
)


def _exact_text(value, name):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty exact text")


@dataclass(frozen=True)
class StoryChoiceTransition:
    choice_key: str
    def __post_init__(self): _exact_text(self.choice_key, "choice_key")


@dataclass(frozen=True)
class StorySpatialTrigger:
    cell: SceneCell
    transition: StoryChoiceTransition
    def __post_init__(self):
        if type(self.cell) is not SceneCell or type(self.transition) is not StoryChoiceTransition:
            raise ValueError("trigger requires exact cell and transition")


@dataclass(frozen=True)
class StoryEntrySpawn:
    source_node_id: str
    position: PlayerPosition
    def __post_init__(self):
        _exact_text(self.source_node_id, "source_node_id")
        if type(self.position) is not PlayerPosition:
            raise ValueError("entry position must be a PlayerPosition")


@dataclass(frozen=True)
class StorySpatialDefinition:
    node_id: str
    spec: SceneSpatialSpec
    player_spawn: PlayerPosition
    entry_spawns: tuple[StoryEntrySpawn, ...] = ()
    triggers: tuple[StorySpatialTrigger, ...] = ()
    def __post_init__(self):
        _exact_text(self.node_id, "node_id")
        if type(self.spec) is not SceneSpatialSpec or self.spec.scene_id != self.node_id:
            raise ValueError("spec must exactly match story node")
        if type(self.player_spawn) is not PlayerPosition:
            raise ValueError("player_spawn must be a PlayerPosition")
        if type(self.entry_spawns) is not tuple or type(self.triggers) is not tuple:
            raise ValueError("story spatial containers must be tuples")
        trigger_cells = {trigger.cell for trigger in self.triggers}
        if len(trigger_cells) != len(self.triggers):
            raise ValueError("duplicate story trigger cell")
        sources = {entry.source_node_id for entry in self.entry_spawns}
        if len(sources) != len(self.entry_spawns):
            raise ValueError("duplicate story entry source")
        for position in (self.player_spawn,) + tuple(e.position for e in self.entry_spawns):
            if not can_player_occupy(self.spec, position):
                raise ValueError("story spawn must be occupiable")
            if SceneCell(position.x, position.y) in trigger_cells:
                raise ValueError("story spawn must not occupy a trigger")
        for trigger in self.triggers:
            if not can_player_occupy(self.spec, PlayerPosition(trigger.cell.x, trigger.cell.y)):
                raise ValueError("story trigger must be occupiable")


@dataclass(frozen=True)
class StorySpatialCatalog:
    definitions: tuple[StorySpatialDefinition, ...]
    def __post_init__(self):
        if type(self.definitions) is not tuple:
            raise ValueError("definitions must be a tuple")
        ids = tuple(d.node_id for d in self.definitions)
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate story node")


def story_spatial_definition_for_node(catalog, node_id):
    if type(catalog) is not StorySpatialCatalog or type(node_id) is not str:
        raise ValueError("exact catalog and node ID are required")
    return next((d for d in catalog.definitions if d.node_id == node_id), None)


def story_entry_spawn_from_node(definition, source_node_id):
    if type(definition) is not StorySpatialDefinition or type(source_node_id) is not str:
        raise ValueError("exact definition and source node ID are required")
    entry = next((e for e in definition.entry_spawns if e.source_node_id == source_node_id), None)
    return None if entry is None else entry.position


def story_trigger_at_cell(definition, cell):
    if type(definition) is not StorySpatialDefinition or type(cell) is not SceneCell:
        raise ValueError("exact definition and cell are required")
    return next((t for t in definition.triggers if t.cell == cell), None)


def validate_story_spatial_catalog_topology(catalog, story_graph):
    if type(catalog) is not StorySpatialCatalog:
        raise ValueError("exact story spatial catalog required")
    for definition in catalog.definitions:
        node = story_graph.node(definition.node_id)
        choices = {choice.key: choice for choice in node.choices}
        for trigger in definition.triggers:
            choice = choices.get(trigger.transition.choice_key)
            if choice is None:
                raise ValueError("story trigger choice does not exist")
            destinations = {choice.next, choice.on_success, choice.on_failure} - {None}
            for destination in destinations:
                target = story_spatial_definition_for_node(catalog, destination)
                if target is not None and story_entry_spawn_from_node(target, definition.node_id) is None:
                    raise ValueError("story destination lacks source entry spawn")


def canonical_action_for_story_spatial_step(*, current_node_id, current_position, step, definition):
    if current_node_id != definition.node_id:
        raise ValueError("story definition does not match current node")
    candidate = player_position_after_step(current_position, step)
    trigger = story_trigger_at_cell(definition, SceneCell(candidate.x, candidate.y))
    if trigger is not None:
        return StoryChoiceAction(trigger.transition.choice_key)
    return MovePlayerToPositionAction(candidate)


def _open_spec(node_id):
    cells = tuple(SceneCell(x, y) for y in range(5) for x in range(7))
    return SceneSpatialSpec(node_id, SceneBounds(7, 5), cells, ())


def _definition(node_id, choices, entries=()):
    trigger_cells = (SceneCell(5, 2), SceneCell(1, 2))
    return StorySpatialDefinition(
        node_id, _open_spec(node_id), PlayerPosition(3, 2), entries,
        tuple(StorySpatialTrigger(trigger_cells[i], StoryChoiceTransition(key))
              for i, key in enumerate(choices)),
    )


GOBLIN_STORY_SPATIAL_CATALOG = StorySpatialCatalog((
    _definition("forest", ("road", "bush")),
    _definition("sneak_ok", ("cave",), (StoryEntrySpawn("forest", PlayerPosition(3, 2)),)),
    _definition("sneak_fail", ("cave",), (StoryEntrySpawn("forest", PlayerPosition(3, 2)),)),
    _definition("cave_hall", ("front", "sneak")),
))


def current_story_spatial_definition(scenario_id, node_id):
    if scenario_id != "goblin":
        return None
    return story_spatial_definition_for_node(GOBLIN_STORY_SPATIAL_CATALOG, node_id)
