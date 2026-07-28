from datetime import datetime, timezone

from app.models import Chamber, FeedItem, PartyLane
from app.normalize import normalize_items
from app.utils import compute_content_hash


def make_item(
    title: str,
    url: str,
    *,
    published_at: datetime | None,
    first_seen_at: datetime,
    summary: str = "",
) -> FeedItem:
    return FeedItem(
        source_id="source",
        source_name="Source",
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        title=title,
        url=url,
        published_at=published_at,
        first_seen_at=first_seen_at,
        last_seen_at=first_seen_at,
        summary=summary,
    )


def test_normalize_deduplicates_hashes_and_sorts_items():
    early = datetime(2026, 7, 1, tzinfo=timezone.utc)
    late = datetime(2026, 7, 20, tzinfo=timezone.utc)
    undated_seen = datetime(2026, 7, 10, tzinfo=timezone.utc)
    duplicate = make_item(
        "Older release",
        "https://example.com/older",
        published_at=early,
        first_seen_at=early,
        summary="First copy",
    )
    items = [
        duplicate,
        make_item(
            "Undated release",
            "https://example.com/undated",
            published_at=None,
            first_seen_at=undated_seen,
        ),
        make_item(
            "Newest release",
            "https://example.com/newest",
            published_at=late,
            first_seen_at=late,
            summary="Source summary",
        ),
        duplicate.model_copy(update={"summary": "Second copy"}),
    ]

    result = normalize_items(items)

    assert [item.title for item in result] == [
        "Newest release",
        "Undated release",
        "Older release",
    ]
    assert result[-1].summary == "First copy"
    assert result[0].content_hash == compute_content_hash("Newest release Source summary")
    assert all(item.content_hash for item in result)
