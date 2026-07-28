import pytest

import app.parsers.date_link_list  # noqa: F401
import app.parsers.drupal_node  # noqa: F401
import app.parsers.house_gop  # noqa: F401
import app.parsers.post_list  # noqa: F401
import app.parsers.senate_hsgac  # noqa: F401
import app.parsers.senate_press  # noqa: F401
from app.models import Chamber, ItemType, PartyLane, SourceConfig
from app.parsers import get_parser
from tests.conftest import load_fixture


def make_source(parser_id: str, **overrides) -> SourceConfig:
    values = {
        "id": f"test_{parser_id}",
        "name": f"Test {parser_id}",
        "committee": "Test Committee",
        "chamber": Chamber.house,
        "party_lane": PartyLane.majority,
        "url": "https://example.com/",
        "collection": "press",
        "kind": ItemType.press_release,
        "tier": "tier1",
        "parser": parser_id,
        "enabled": True,
    }
    values.update(overrides)
    return SourceConfig(**values)


@pytest.mark.parametrize(
    (
        "fixture_name",
        "parser_id",
        "source_overrides",
        "expected",
    ),
    [
        ("energy_commerce_press", "energy_commerce_press", {}, (9, 0, 9, 0)),
        (
            "homeland_dems_correspondence",
            "homeland_dems_correspondence",
            {"kind": ItemType.letter, "party_lane": PartyLane.minority},
            (20, 20, 20, 0),
        ),
        ("homeland_house_press", "homeland_house_press", {}, (20, 20, 0, 0)),
        ("hsgac_news", "hsgac_news", {"chamber": Chamber.senate}, (10, 10, 0, 0)),
        (
            "judiciary_dems_press",
            "judiciary_dems_press",
            {"party_lane": PartyLane.minority},
            (10, 10, 10, 0),
        ),
        (
            "judiciary_house_letters",
            "judiciary_house_letters",
            {"kind": ItemType.letter},
            (20, 20, 0, 20),
        ),
        ("judiciary_house_press", "judiciary_house_press", {}, (10, 10, 7, 0)),
        (
            "oversight_dems_letters",
            "oversight_dems_letters",
            {"kind": ItemType.letter, "party_lane": PartyLane.minority},
            (15, 15, 0, 0),
        ),
        (
            "oversight_dems_press",
            "oversight_dems_press",
            {"party_lane": PartyLane.minority},
            (20, 20, 0, 0),
        ),
        (
            "oversight_house_letters",
            "oversight_house_letters",
            {"kind": ItemType.letter},
            (10, 10, 0, 10),
        ),
        ("oversight_house_press", "oversight_house_press", {}, (10, 10, 10, 0)),
        (
            "psi_library",
            "psi_library",
            {
                "chamber": Chamber.senate,
                "kind": ItemType.document,
                "party_lane": PartyLane.committee,
                "recent_item_limit": 50,
            },
            (20, 20, 0, 0),
        ),
        (
            "senate_judiciary_press",
            "senate_judiciary_press",
            {"chamber": Chamber.senate},
            (20, 20, 0, 0),
        ),
    ],
)
def test_saved_parser_fixture_contracts(
    fixture_name,
    parser_id,
    source_overrides,
    expected,
):
    items = get_parser(parser_id)(
        load_fixture(fixture_name),
        make_source(parser_id, **source_overrides),
    )

    actual = (
        len(items),
        sum(item.published_at is not None for item in items),
        sum(bool(item.summary) for item in items),
        sum(item.is_pdf for item in items),
    )
    assert actual == expected


def test_remaining_registered_parsers_keep_their_item_type_and_date_rules():
    energy_items = get_parser("energy_commerce_letters")(
        load_fixture("energy_commerce_press"),
        make_source("energy_commerce_letters", kind=ItemType.letter),
    )
    judiciary_items = get_parser("judiciary_dems_letters")(
        """
        <div>
          July 20, 2026
          <a href="/letters/request-for-agency-records">Request for agency records</a>
        </div>
        <a href="/letters/">Letters</a>
        """,
        make_source(
            "judiciary_dems_letters",
            kind=ItemType.letter,
            party_lane=PartyLane.minority,
        ),
    )

    assert len(energy_items) == 9
    assert all(item.item_type == ItemType.letter for item in energy_items)
    assert len(judiciary_items) == 1
    assert judiciary_items[0].published_at is not None
    assert judiciary_items[0].party_lane == PartyLane.minority
