from __future__ import annotations

from app.models import FeedItem
from app.utils import compute_content_hash


def deduplicate(items: list[FeedItem]) -> list[FeedItem]:
    """Remove duplicate items by item_id, keeping the first occurrence."""
    seen: set[str] = set()
    unique: list[FeedItem] = []
    for item in items:
        if item.item_id not in seen:
            seen.add(item.item_id)
            unique.append(item)
    return unique


def sort_by_date(items: list[FeedItem]) -> list[FeedItem]:
    """Sort items by published_at descending. Items without dates go last."""
    return sorted(
        items,
        key=lambda x: x.published_at or x.first_seen_at,
        reverse=True,
    )


def add_content_hashes(items: list[FeedItem]) -> list[FeedItem]:
    """Compute content_hash for each item from title + summary."""
    result = []
    for item in items:
        content = f"{item.title} {item.summary}"
        result.append(item.model_copy(update={"content_hash": compute_content_hash(content)}))
    return result


def normalize_items(items: list[FeedItem]) -> list[FeedItem]:
    """Full normalization pipeline: deduplicate, hash, sort."""
    items = deduplicate(items)
    items = add_content_hashes(items)
    items = sort_by_date(items)
    return items
