"""Fixture-based parser tests.

Each test loads saved HTML, runs the parser, and asserts:
- Items were found
- First item has title, url, and date (where applicable)
"""
import app.parsers.date_link_list  # noqa: F401
import app.parsers.drupal_node  # noqa: F401
import app.parsers.house_gop  # noqa: F401
import app.parsers.post_list  # noqa: F401
import app.parsers.senate_hsgac  # noqa: F401
import app.parsers.senate_press  # noqa: F401
from app.models import Chamber, ItemType, PartyLane, SourceConfig, SourceTier
from app.parsers import get_parser
from tests.conftest import load_fixture


def _make_source(parser_id: str, url: str = "https://example.com", **kwargs) -> SourceConfig:
    defaults = dict(
        id=f"test_{parser_id}",
        name=f"Test {parser_id}",
        committee="Test Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        url=url,
        collection="press",
        kind=ItemType.press_release,
        tier=SourceTier.tier1,
        parser=parser_id,
        enabled=True,
    )
    defaults.update(kwargs)
    return SourceConfig(**defaults)


class TestOverightHousePress:
    def test_parses_items(self):
        html = load_fixture("oversight_house_press")
        source = _make_source("oversight_house_press", url="https://oversight.house.gov/release/")
        parser = get_parser("oversight_house_press")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None


class TestOverightHouseLetters:
    def test_parses_items(self):
        html = load_fixture("oversight_house_letters")
        source = _make_source("oversight_house_letters", url="https://oversight.house.gov/letter/",
                              kind=ItemType.letter)
        parser = get_parser("oversight_house_letters")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")


class TestHomelandHousePress:
    def test_parses_items(self):
        html = load_fixture("homeland_house_press")
        source = _make_source("homeland_house_press", url="https://homeland.house.gov/press/")
        parser = get_parser("homeland_house_press")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None


class TestOversightDemsPress:
    def test_parses_items(self):
        html = load_fixture("oversight_dems_press")
        source = _make_source("oversight_dems_press",
                              url="https://oversightdemocrats.house.gov/news/press-releases",
                              party_lane=PartyLane.minority)
        parser = get_parser("oversight_dems_press")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None


class TestOversightDemsLetters:
    def test_parses_items(self):
        html = load_fixture("oversight_dems_letters")
        source = _make_source("oversight_dems_letters",
                              url="https://oversightdemocrats.house.gov/letters",
                              kind=ItemType.letter, party_lane=PartyLane.minority)
        parser = get_parser("oversight_dems_letters")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")


class TestJudiciaryDemsPress:
    def test_parses_items(self):
        html = load_fixture("judiciary_dems_press")
        source = _make_source("judiciary_dems_press",
                              url="https://democrats-judiciary.house.gov/media-center/press-releases",
                              party_lane=PartyLane.minority)
        parser = get_parser("judiciary_dems_press")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None


class TestHomelandDemsCorrespondence:
    def test_parses_items(self):
        html = load_fixture("homeland_dems_correspondence")
        source = _make_source("homeland_dems_correspondence",
                              url="https://democrats-homeland.house.gov/news/correspondence",
                              kind=ItemType.letter, party_lane=PartyLane.minority)
        parser = get_parser("homeland_dems_correspondence")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None


class TestJudiciaryHouseLetters:
    def test_parses_items(self):
        html = load_fixture("judiciary_house_letters")
        source = _make_source("judiciary_house_letters",
                              url="https://judiciary.house.gov/documents/letters",
                              kind=ItemType.letter)
        parser = get_parser("judiciary_house_letters")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")


class TestEnergyCommercePress:
    def test_parses_items(self):
        html = load_fixture("energy_commerce_press")
        source = _make_source("energy_commerce_press",
                              url="https://energycommerce.house.gov/news/press-release")
        parser = get_parser("energy_commerce_press")
        items = parser(html, source)

        assert len(items) >= 3
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")


class TestSenateJudiciaryPress:
    def test_parses_items(self):
        html = load_fixture("senate_judiciary_press")
        source = _make_source("senate_judiciary_press",
                              url="https://www.judiciary.senate.gov/press/majority",
                              chamber=Chamber.senate)
        parser = get_parser("senate_judiciary_press")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None


class TestHsgacNews:
    def test_parses_items(self):
        html = load_fixture("hsgac_news")
        source = _make_source("hsgac_news",
                              url="https://www.hsgac.senate.gov/media/majority-news/",
                              chamber=Chamber.senate)
        parser = get_parser("hsgac_news")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")


class TestPsiLibrary:
    def test_parses_items(self):
        html = load_fixture("psi_library")
        source = _make_source("psi_library",
                              url="https://www.hsgac.senate.gov/subcommittees/investigations/library/",
                              chamber=Chamber.senate, kind=ItemType.document,
                              party_lane=PartyLane.committee, recent_item_limit=50)
        parser = get_parser("psi_library")
        items = parser(html, source)

        assert len(items) >= 5
        first = items[0]
        assert first.title
        assert first.url.startswith("https://")
        assert first.published_at is not None
