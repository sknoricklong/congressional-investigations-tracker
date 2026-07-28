from pathlib import Path

import pytest

from app import cli as cli_module
from app.config import get_enabled_sources, get_source_by_id, load_sources
from app.models import Chamber, PartyLane, SourceTier
from app.parsers import get_parser

SOURCES_YAML = """
sources:
  - id: enabled_source
    name: Enabled source
    committee: Test Committee
    chamber: House
    party_lane: majority
    url: https://example.com/enabled
    collection: press
    kind: press_release
    tier: tier1
    parser: oversight_house_press
    enabled: true
  - id: planned_source
    name: Planned source
    committee: Test Committee
    chamber: Senate
    party_lane: minority
    url: https://example.com/planned
    collection: letters
    kind: letter
    tier: tier2
    parser: planned_parser
    enabled: false
"""


def write_sources(path: Path) -> Path:
    path.write_text(SOURCES_YAML)
    return path


def test_load_sources_validates_fields_and_defaults(tmp_path):
    sources = load_sources(write_sources(tmp_path / "sources.yml"))

    assert [source.id for source in sources] == ["enabled_source", "planned_source"]
    assert sources[0].chamber == Chamber.house
    assert sources[0].party_lane == PartyLane.majority
    assert sources[0].tier == SourceTier.tier1
    assert sources[0].recent_item_limit == 20
    assert sources[0].detail_fetch == "none"


def test_get_enabled_sources_filters_disabled_entries(tmp_path):
    sources = get_enabled_sources(write_sources(tmp_path / "sources.yml"))

    assert [source.id for source in sources] == ["enabled_source"]


def test_get_source_by_id_returns_match_and_lists_available_ids(tmp_path):
    config_path = write_sources(tmp_path / "sources.yml")

    assert get_source_by_id("planned_source", config_path).enabled is False
    with pytest.raises(KeyError, match="enabled_source.*planned_source"):
        get_source_by_id("missing", config_path)


def test_live_registry_has_unique_ids_and_registered_enabled_parsers():
    sources = load_sources()
    enabled = get_enabled_sources()

    assert cli_module.cli
    assert len(sources) == 30
    assert len(enabled) == 16
    assert len({source.id for source in sources}) == len(sources)
    for source in enabled:
        assert callable(get_parser(source.parser)), source.id
