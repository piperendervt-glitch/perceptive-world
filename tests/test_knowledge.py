from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from trpg_core.knowledge import (
    KnowledgeCatalogError,
    KnowledgeMemoryTagId,
    goblin_knowledge_catalog,
    load_knowledge_catalog,
    production_knowledge_path,
)
from trpg_core.world import WorldObjectId


EXPECTED_FACTS = {
    "goblin:location/well": (
        ("shape", "well_like", 0), ("material", "stone", 1),
        ("age", "old", 1), ("pulley", "recent", 2),
        ("rope", "worn", 2), ("mark", "faded_emblem", 3),
    ),
    "goblin:location/shrine": (
        ("shape", "small_shrine", 0), ("material", "weathered_stone", 1),
        ("offering", "kept_clean", 2), ("condition", "quietly_usable", 3),
    ),
    "goblin:location/lookout": (
        ("shape", "lookout_tower", 0), ("material", "timber", 1),
        ("view", "forest_edge_visible", 2), ("condition", "stable_vantage", 3),
    ),
    "goblin:location/herbhut": (
        ("shape", "small_hut", 0), ("scent", "dried_herbs", 1),
        ("stock", "prepared_bundles", 2), ("condition", "carefully_sorted", 3),
    ),
    "goblin:location/elderhouse": (
        ("shape", "large_house", 0), ("material", "old_timber", 1),
        ("records", "village_notes", 2),
        ("condition", "orderly_meeting_place", 3),
    ),
}

EXPECTED_MEMORY = {
    "goblin:memory/well-faded-emblem": ("goblin:location/well", "mark", (),),
    "goblin:memory/shrine-blessing-site": (
        "goblin:location/shrine", "condition", ("shrine",),
    ),
    "goblin:memory/lookout-surveyed": (
        "goblin:location/lookout", "view", ("scout",),
    ),
    "goblin:memory/herbhut-supplies": (
        "goblin:location/herbhut", "stock", ("herbs",),
    ),
    "goblin:memory/elder-intel": (
        "goblin:location/elderhouse", "records", ("elder",),
    ),
}


def _write(tmp_path, text):
    path = tmp_path / "knowledge.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _production_text():
    return production_knowledge_path("goblin").read_text(encoding="utf-8")


def test_production_catalog_is_complete_immutable_and_deterministic():
    catalog = goblin_knowledge_catalog()
    assert catalog.schema_version == 1 and catalog.scenario_id == "goblin"
    assert tuple(str(item.object_id.scenario_id) + ":" + item.object_id.local_id
                 for item in catalog.objects) == tuple(sorted(EXPECTED_FACTS))
    assert {
        f"{item.object_id.scenario_id}:{item.object_id.local_id}": tuple(
            (fact.key, fact.value, fact.lod) for fact in item.facts
        ) for item in catalog.objects
    } == EXPECTED_FACTS
    assert tuple(str(item.tag_id) for item in catalog.memory_tags) == tuple(sorted(EXPECTED_MEMORY))
    for tag in catalog.memory_tags:
        object_id, fact_key, actions = EXPECTED_MEMORY[str(tag.tag_id)]
        assert tuple(
            (f"{ref.object_id.scenario_id}:{ref.object_id.local_id}", ref.fact_key)
            for ref in tag.required_facts
        ) == ((object_id, fact_key),)
        assert tag.required_completed_actions == actions
        assert tag.label_key.startswith("memory.")
    assert goblin_knowledge_catalog() is catalog
    with pytest.raises((FrozenInstanceError, AttributeError)):
        catalog.scenario_id = "changed"


def test_exact_catalog_lookups_have_no_fallback():
    catalog = goblin_knowledge_catalog()
    well = WorldObjectId("goblin", "location/well")
    assert catalog.object(well).fact("mark").value == "faded_emblem"
    assert catalog.fact(well, "mark").lod == 3
    assert catalog.fact(well, "mar") is None
    assert catalog.object(WorldObjectId("goblin", "location/wel")) is None
    tag = KnowledgeMemoryTagId("goblin", "memory/well-faded-emblem")
    assert catalog.memory_tag(tag).label_key == "memory.well.faded_emblem"
    assert catalog.memory_tag(KnowledgeMemoryTagId("goblin", "memory/well")) is None
    with pytest.raises(ValueError, match="exact WorldObjectId"):
        catalog.object("goblin:location/well")


@pytest.mark.parametrize("old,new,match", [
    ("schema_version: 1", "", "missing top-level field"),
    ("schema_version: 1", "schema_version: 2", "unsupported"),
    ("scenario_id: goblin", "scenario_id: other", "does not match"),
    ("objects:", "unknown: true\nobjects:", "unknown top-level field"),
    ("    facts:", "    unknown: true\n    facts:", "unknown object"),
    ("        value: well_like", "        unknown: true\n        value: well_like", "unknown fact"),
    ("    required_facts:", "    unknown: true\n    required_facts:", "unknown memory tag"),
    ("  goblin:location/well:", "  other:location/well:", "namespace"),
    ("  goblin:location/well:", "  malformed:", "malformed object"),
    ("  goblin:memory/well-faded-emblem:", "  goblin:tag/well:", "malformed memory"),
    ("      shape:", "      '':", "fact key"),
    ("        value: well_like", "        value: ''", "fact shape value"),
    ("        lod: 0", "        lod: true", "exact int"),
    ("        lod: 0", "        lod: 0.0", "exact int"),
    ("        lod: 0", "        lod: '0'", "exact int"),
    ("        lod: 0", "        lod: 4", "exact int"),
    ("        label_key: well.shape.well_like", "        label_key: missing.label", "unknown fact label"),
    ("        label_key: well.shape.well_like\n", "", "missing fact shape field"),
    ("    label_key: memory.well.faded_emblem", "    label_key: memory.unknown", "unknown memory label"),
    ("    label_key: memory.well.faded_emblem\n", "", "missing memory tag"),
    ("        fact_key: mark", "        fact_key: missing", "dangling"),
    ("      - shrine", "      - missing", "unknown completed action"),
])
def test_strict_schema_rejects_invalid_documents(tmp_path, old, new, match):
    text = _production_text()
    assert old in text
    with pytest.raises(KnowledgeCatalogError, match=match):
        load_knowledge_catalog(
            _write(tmp_path, text.replace(old, new, 1)),
            expected_scenario_id="goblin",
        )


@pytest.mark.parametrize("text", [
    "schema_version: 1\nschema_version: 1\nscenario_id: goblin\nobjects: {}\nmemory_tags: {}\n",
    "schema_version: 1\nscenario_id: goblin\nobjects:\n  goblin:location/well:\n    facts: {}\n  goblin:location/well:\n    facts: {}\nmemory_tags: {}\n",
    "schema_version: 1\nscenario_id: goblin\nobjects:\n  goblin:location/well:\n    facts:\n      shape: {value: well_like, lod: 0, label_key: well.shape.well_like}\n      shape: {value: well_like, lod: 0, label_key: well.shape.well_like}\nmemory_tags: {}\n",
    "schema_version: 1\nscenario_id: goblin\nobjects: {}\nmemory_tags:\n  goblin:memory/well-faded-emblem: {}\n  goblin:memory/well-faded-emblem: {}\n",
])
def test_duplicate_yaml_keys_are_rejected_before_normalization(tmp_path, text):
    with pytest.raises(KnowledgeCatalogError, match="duplicate YAML key"):
        load_knowledge_catalog(_write(tmp_path, text), expected_scenario_id="goblin")


def test_duplicate_prerequisites_are_rejected(tmp_path):
    text = _production_text()
    fact = "      - object_id: goblin:location/well\n        fact_key: mark\n"
    with pytest.raises(KnowledgeCatalogError, match="duplicate required fact"):
        load_knowledge_catalog(
            _write(tmp_path, text.replace(fact, fact + fact, 1)),
            expected_scenario_id="goblin",
        )
    with pytest.raises(KnowledgeCatalogError, match="duplicate completed action"):
        load_knowledge_catalog(
            _write(tmp_path, text.replace("      - shrine\n", "      - shrine\n      - shrine\n", 1)),
            expected_scenario_id="goblin",
        )


def test_missing_and_malformed_files_fail_explicitly(tmp_path):
    with pytest.raises(KnowledgeCatalogError, match="cannot load"):
        load_knowledge_catalog(tmp_path / "missing.yaml", expected_scenario_id="goblin")
    with pytest.raises(KnowledgeCatalogError, match="cannot load"):
        load_knowledge_catalog(_write(tmp_path, "objects: ["), expected_scenario_id="goblin")
