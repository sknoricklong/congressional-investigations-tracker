"""Tests for the diff engine."""
from datetime import datetime, timezone

from app.diff import diff_items
from app.models import (
    Chamber,
    FeedItem,
    ItemStatus,
    ItemType,
    PartyLane,
    SourceTier,
)


def _make_item(title: str, url: str = "https://example.com/1", content_hash: str = "abc123",
               **kwargs) -> FeedItem:
    defaults = dict(
        source_id="test",
        source_name="Test",
        committee="Test",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        title=title,
        url=url,
        item_type=ItemType.press_release,
        content_hash=content_hash,
        first_seen_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        source_tier=SourceTier.tier1,
    )
    defaults.update(kwargs)
    return FeedItem(**defaults)


class TestDiffItems:
    def test_all_new(self):
        current = [_make_item("Item A"), _make_item("Item B", url="https://example.com/2")]
        previous: list[FeedItem] = []
        result = diff_items(current, previous)

        assert len(result) == 2
        assert all(i.status == ItemStatus.new for i in result)

    def test_all_unchanged(self):
        items = [_make_item("Item A"), _make_item("Item B", url="https://example.com/2")]
        result = diff_items(items, items)

        assert len(result) == 2
        assert all(i.status == ItemStatus.unchanged for i in result)

    def test_updated_item(self):
        prev = [_make_item("Item A", content_hash="old_hash")]
        curr = [_make_item("Item A", content_hash="new_hash")]
        result = diff_items(curr, prev)

        assert len(result) == 1
        assert result[0].status == ItemStatus.updated

    def test_mix_of_new_and_unchanged(self):
        prev = [_make_item("Item A")]
        curr = [
            _make_item("Item A"),
            _make_item("Item B", url="https://example.com/2"),
        ]
        result = diff_items(curr, prev)

        statuses = {i.title: i.status for i in result}
        assert statuses["Item A"] == ItemStatus.unchanged
        assert statuses["Item B"] == ItemStatus.new

    def test_preserves_first_seen_at(self):
        old_time = datetime(2026, 3, 1, tzinfo=timezone.utc)
        prev = [_make_item("Item A", first_seen_at=old_time)]
        curr = [_make_item("Item A")]
        result = diff_items(curr, prev)

        assert result[0].first_seen_at == old_time
