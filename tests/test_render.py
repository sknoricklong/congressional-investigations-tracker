import json
from datetime import datetime, timezone

from app.models import Chamber, FeedItem, PartyLane, SourceConfig
from app.render import render_site


def make_item(
    title: str,
    url: str,
    published_at: datetime,
    summary: str,
) -> FeedItem:
    return FeedItem(
        source_id="source",
        source_name="Enabled Source",
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        first_seen_at=published_at,
        last_seen_at=published_at,
    )


def make_source(name: str, enabled: bool) -> SourceConfig:
    return SourceConfig(
        id=name.lower().replace(" ", "_"),
        name=name,
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        url=f"https://example.com/{name.lower().replace(' ', '-')}",
        collection="press",
        kind="press_release",
        tier="tier1",
        parser="parser",
        enabled=enabled,
        why_relevant=f"Why {name} matters.",
    )


def test_render_writes_current_page_and_json_feed_shapes_to_temp_dir(tmp_path):
    newer = datetime(2026, 7, 20, tzinfo=timezone.utc)
    older = datetime(2026, 7, 10, tzinfo=timezone.utc)
    items = [
        make_item("Newest", "https://example.com/new", newer, "Source summary"),
        make_item("Duplicate URL", "https://example.com/new", older, "Other summary"),
        make_item("No summary", "https://example.com/blank", older, ""),
    ]
    enabled = make_source("Enabled Source", True)
    planned = make_source("Planned Source", False)

    render_site(
        items,
        None,
        tmp_path,
        sources_config=[enabled],
        all_sources_config=[enabled, planned],
    )

    html = (tmp_path / "index.html").read_text()
    feed = json.loads((tmp_path / "feed.json").read_text())

    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert feed["title"] == "Congressional Investigations Monitor"
    assert [item["title"] for item in feed["items"]] == ["Newest", "No summary"]
    assert set(feed["items"][0]) == {
        "id",
        "title",
        "url",
        "date_published",
        "summary",
        "tags",
        "_congress_monitor",
    }
    assert set(feed["items"][0]["_congress_monitor"]) == {
        "source_id",
        "source_name",
        "party_lane",
        "status",
        "is_pdf",
        "first_seen_at",
        "cluster_id",
        "summary_generated",
    }
    assert feed["items"][0]["_congress_monitor"]["summary_generated"] is False
    assert feed["items"][1]["_congress_monitor"]["summary_generated"] is True
    assert "Planned Source" in html
    assert "Why Planned Source matters." in html
    assert "Duplicate URL" not in html
