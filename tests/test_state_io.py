import json
from datetime import datetime, timezone

from app.diff import append_history, load_state, save_state
from app.models import Chamber, FeedItem, ItemStatus, PartyLane


def make_item(title: str, url: str, status: ItemStatus) -> FeedItem:
    seen = datetime(2026, 7, 20, tzinfo=timezone.utc)
    return FeedItem(
        source_id="source",
        source_name="Source",
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        title=title,
        url=url,
        published_at=seen,
        first_seen_at=seen,
        last_seen_at=seen,
        content_hash=f"hash-{title}",
        status=status,
    )


def test_load_state_returns_empty_for_missing_or_invalid_file(tmp_path):
    assert load_state(tmp_path) == {}

    (tmp_path / "state.json").write_text("{invalid")
    assert load_state(tmp_path) == {}


def test_save_and_load_state_round_trip_without_leaving_temp_file(tmp_path):
    item = make_item("Saved release", "https://example.com/saved", ItemStatus.unchanged)

    save_state({"source": [item]}, tmp_path)
    loaded = load_state(tmp_path)

    assert list(loaded) == ["source"]
    assert loaded["source"][0].model_dump(mode="json") == item.model_dump(mode="json")
    assert not (tmp_path / "state.json.tmp").exists()


def test_append_history_writes_only_new_and_updated_records(tmp_path):
    items = [
        make_item("New release", "https://example.com/new", ItemStatus.new),
        make_item("Changed release", "https://example.com/changed", ItemStatus.updated),
        make_item("Old release", "https://example.com/old", ItemStatus.unchanged),
    ]

    append_history(items, tmp_path)
    rows = [
        json.loads(line)
        for line in (tmp_path / "history.jsonl").read_text().splitlines()
    ]

    assert [row["title"] for row in rows] == ["New release", "Changed release"]
    assert [row["status"] for row in rows] == ["new", "updated"]

    append_history([items[-1]], tmp_path)
    assert len((tmp_path / "history.jsonl").read_text().splitlines()) == 2
