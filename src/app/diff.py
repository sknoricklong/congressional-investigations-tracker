from __future__ import annotations

import json
import logging
from pathlib import Path

from app.models import FeedItem, ItemStatus

logger = logging.getLogger(__name__)


def load_state(data_dir: Path) -> dict[str, list[FeedItem]]:
    """Load previous state from data/state.json. Returns empty dict on first run."""
    state_path = data_dir / "state.json"
    if not state_path.exists():
        return {}

    try:
        raw = json.loads(state_path.read_text())
        result: dict[str, list[FeedItem]] = {}
        for source_id, item_dicts in raw.items():
            result[source_id] = [FeedItem(**d) for d in item_dicts]
        return result
    except Exception as e:
        logger.warning(f"Could not load state from {state_path}: {e}. Starting fresh.")
        return {}


def save_state(items_by_source: dict[str, list[FeedItem]], data_dir: Path) -> None:
    """Save current state to data/state.json (atomic write via temp file)."""
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "state.json"
    tmp_path = data_dir / "state.json.tmp"

    serialized: dict[str, list[dict]] = {}
    for source_id, items in items_by_source.items():
        serialized[source_id] = [item.model_dump(mode="json") for item in items]

    tmp_path.write_text(json.dumps(serialized, indent=2, default=str))
    tmp_path.rename(state_path)


def diff_items(
    current: list[FeedItem],
    previous: list[FeedItem],
) -> list[FeedItem]:
    """Compare current items against previous state. Returns items with status set.

    - new: item_id not in previous
    - updated: same item_id, different content_hash
    - unchanged: same item_id, same content_hash
    """
    prev_by_id = {item.item_id: item for item in previous}
    result: list[FeedItem] = []

    for item in current:
        prev = prev_by_id.get(item.item_id)
        if prev is None:
            result.append(item.model_copy(update={"status": ItemStatus.new}))
        elif item.content_hash != prev.content_hash:
            result.append(item.model_copy(update={
                "status": ItemStatus.updated,
                "first_seen_at": prev.first_seen_at,
            }))
        else:
            result.append(item.model_copy(update={
                "status": ItemStatus.unchanged,
                "first_seen_at": prev.first_seen_at,
            }))

    return result


def append_history(items: list[FeedItem], data_dir: Path) -> None:
    """Append new and updated items to data/history.jsonl."""
    data_dir.mkdir(parents=True, exist_ok=True)
    history_path = data_dir / "history.jsonl"

    new_or_updated = [
        item for item in items if item.status in (ItemStatus.new, ItemStatus.updated)
    ]
    if not new_or_updated:
        return

    with open(history_path, "a") as f:
        for item in new_or_updated:
            line = json.dumps(item.model_dump(mode="json"), default=str)
            f.write(line + "\n")
