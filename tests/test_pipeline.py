import json
from datetime import datetime, timedelta, timezone

import pytest

from app import pipeline
from app.models import Chamber, FeedItem, PartyLane, RunResult, RunSummary, SourceConfig


def make_source(parser: str = "test_parser") -> SourceConfig:
    return SourceConfig(
        id="source",
        name="Source",
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        url="https://example.com/releases",
        collection="press",
        kind="press_release",
        tier="tier1",
        parser=parser,
    )


def make_item(
    title: str,
    url: str = "https://example.com/release",
    published_at: datetime | None = None,
) -> FeedItem:
    seen = datetime(2026, 7, 20, tzinfo=timezone.utc)
    return FeedItem(
        source_id="source",
        source_name="Source",
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        title=title,
        url=url,
        published_at=published_at,
        first_seen_at=seen,
        last_seen_at=seen,
    )


@pytest.mark.asyncio
async def test_parser_error_marks_source_failed_and_saves_debug_fixture(monkeypatch):
    saved = []

    async def fake_fetch_source(_source, _client):
        return ["<html>bad listing</html>"]

    def bad_parser(_html, _source):
        raise ValueError("broken fixture")

    monkeypatch.setattr(pipeline, "fetch_source", fake_fetch_source)
    monkeypatch.setattr(pipeline, "get_parser", lambda _parser: bad_parser)
    monkeypatch.setattr(
        pipeline,
        "_save_debug_fixture",
        lambda source_id, html: saved.append((source_id, html)),
    )

    items, result = await pipeline.process_source(make_source(), object())

    assert items == []
    assert result.success is False
    assert result.errors == ["Parse error: broken fixture"]
    assert saved == [("source", "<html>bad listing</html>")]


@pytest.mark.asyncio
async def test_missing_date_is_loaded_from_detail_page(monkeypatch):
    async def fake_fetch_source(_source, _client):
        return ["listing"]

    async def fake_fetch_page(url, _client):
        assert url == "https://example.com/release"
        return '<time datetime="2026-07-19">July 19, 2026</time>'

    monkeypatch.setattr(pipeline, "fetch_source", fake_fetch_source)
    monkeypatch.setattr(pipeline, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(
        pipeline,
        "get_parser",
        lambda _parser: lambda _html, _source: [make_item("Release")],
    )

    items, result = await pipeline.process_source(make_source(), object())

    assert result.success is True
    assert result.items_found == 1
    assert items[0].published_at == datetime(2026, 7, 19, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_truncated_title_is_replaced_only_by_matching_detail_title(monkeypatch):
    async def fake_fetch_source(_source, _client):
        return ["listing"]

    async def fake_fetch_page(_url, _client):
        return "<h1>Agency Records Show a Wider Inquiry Into Contracts</h1>"

    dated = datetime(2026, 7, 19, tzinfo=timezone.utc)
    monkeypatch.setattr(pipeline, "fetch_source", fake_fetch_source)
    monkeypatch.setattr(pipeline, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(
        pipeline,
        "get_parser",
        lambda _parser: lambda _html, _source: [
            make_item("Agency Records Show...", published_at=dated)
        ],
    )

    items, _result = await pipeline.process_source(make_source(), object())

    assert items[0].title == "Agency Records Show a Wider Inquiry Into Contracts"
    assert pipeline._same_title_stem("Agency Records Show...", items[0].title)
    assert not pipeline._same_title_stem("Different release...", items[0].title)


def test_detail_extractors_prefer_article_metadata_and_reject_future_dates():
    past = pipeline._extract_date_from_detail(
        '<meta property="article:published_time" content="2026-07-19T10:00:00-04:00">'
    )
    future_text = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%B %d, %Y")
    future = pipeline._extract_date_from_detail(f"<time>{future_text}</time>")

    assert past == datetime(2026, 7, 19, 14, 0, tzinfo=timezone.utc)
    assert future is None
    assert pipeline._extract_title_from_detail("<h1> Full   headline </h1>") == "Full headline"
    assert (
        pipeline._extract_title_from_detail(
            '<meta property="og:title" content="Fallback headline - Committee Site">'
        )
        == "Fallback headline"
    )


def test_health_checks_find_empty_stale_and_regressed_sources():
    now = datetime.now(timezone.utc)
    previous = {
        "source": [
            make_item("Previous", published_at=now - timedelta(days=2)),
            make_item(
                "Previous two",
                url="https://example.com/two",
                published_at=now - timedelta(days=3),
            ),
        ]
    }
    current = {"source": [make_item("Current", published_at=now - timedelta(days=10))]}

    warnings = pipeline.check_health(current, previous)

    assert any(warning.startswith("STALE source:") for warning in warnings)
    assert any("newest date went from" in warning for warning in warnings)
    assert any("item count dropped from 2 to 1" in warning for warning in warnings)
    assert pipeline.check_health({"source": []}, previous) == [
        "REGRESSION source: returned 0 items"
    ]


@pytest.mark.asyncio
async def test_pipeline_renders_previous_state_and_skips_writes_on_regression(monkeypatch):
    source = make_source()
    previous_item = make_item(
        "Previous",
        published_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    rendered = []
    saved = []

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    async def process_source(_source, _client):
        return [], RunResult(source_id=source.id, source_name=source.name)

    monkeypatch.setattr(pipeline, "get_enabled_sources", lambda: [source])
    monkeypatch.setattr(pipeline, "load_sources", lambda: [source])
    monkeypatch.setattr(pipeline, "load_state", lambda _data_dir: {"source": [previous_item]})
    monkeypatch.setattr(pipeline, "create_client", ClientContext)
    monkeypatch.setattr(pipeline, "process_source", process_source)
    monkeypatch.setattr(pipeline, "save_state", lambda *_args: saved.append("state"))
    monkeypatch.setattr(pipeline, "append_history", lambda *_args: saved.append("history"))
    monkeypatch.setattr(
        pipeline,
        "render_site",
        lambda items, *_args, **_kwargs: rendered.append(items),
    )
    monkeypatch.setattr(pipeline, "_save_run_log", lambda *_args: None)

    with pytest.raises(SystemExit) as error:
        await pipeline.run_pipeline()

    assert error.value.code == 1
    assert saved == []
    assert rendered == [[previous_item]]


@pytest.mark.asyncio
async def test_pipeline_saves_current_state_history_and_render_on_success(monkeypatch):
    source = make_source()
    current_item = make_item(
        "Current",
        published_at=datetime.now(timezone.utc),
    )
    saved_state = []
    history = []
    rendered = []
    run_logs = []

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    async def process_source(_source, _client):
        return [current_item], RunResult(
            source_id=source.id,
            source_name=source.name,
            items_found=1,
        )

    monkeypatch.setattr(pipeline, "get_enabled_sources", lambda: [source])
    monkeypatch.setattr(pipeline, "load_sources", lambda: [source])
    monkeypatch.setattr(pipeline, "load_state", lambda _data_dir: {})
    monkeypatch.setattr(pipeline, "create_client", ClientContext)
    monkeypatch.setattr(pipeline, "process_source", process_source)
    monkeypatch.setattr(
        pipeline,
        "save_state",
        lambda state, data_dir: saved_state.append((state, data_dir)),
    )
    monkeypatch.setattr(
        pipeline,
        "append_history",
        lambda items, data_dir: history.append((items, data_dir)),
    )
    monkeypatch.setattr(
        pipeline,
        "render_site",
        lambda items, summary, output_dir, **kwargs: rendered.append(
            (items, summary, output_dir, kwargs)
        ),
    )
    monkeypatch.setattr(
        pipeline,
        "_save_run_log",
        lambda summary, warnings: run_logs.append((summary, warnings)),
    )

    await pipeline.run_pipeline()

    saved_item = saved_state[0][0]["source"][0]
    assert saved_item.status.value == "new"
    assert saved_state[0][1] == pipeline.DATA_DIR
    assert history[0] == ([saved_item], pipeline.DATA_DIR)
    assert rendered[0][0] == [saved_item]
    assert rendered[0][1].total_new == 1
    assert rendered[0][2] == pipeline.SITE_DIR
    assert rendered[0][3]["sources_config"] == [source]
    assert rendered[0][3]["all_sources_config"] == [source]
    assert run_logs[0][1] == []


def test_save_run_log_keeps_summary_shape_and_warnings(tmp_path, monkeypatch):
    started = datetime(2026, 7, 28, 12, tzinfo=timezone.utc)
    summary = RunSummary(
        started_at=started,
        finished_at=started + timedelta(minutes=1),
        sources_attempted=1,
        sources_succeeded=0,
        sources_failed=1,
        total_new=0,
        total_updated=0,
        results=[
            RunResult(
                source_id="source",
                source_name="Source",
                success=False,
                errors=["Parse error: broken"],
            )
        ],
    )
    monkeypatch.setattr(pipeline, "LOGS_DIR", tmp_path)

    pipeline._save_run_log(summary, ["REGRESSION source: returned 0 items"])
    data = json.loads((tmp_path / "last_run.json").read_text())

    assert data["sources_attempted"] == 1
    assert data["results"][0]["success"] is False
    assert data["health_warnings"] == ["REGRESSION source: returned 0 items"]
