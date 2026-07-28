from datetime import datetime, timezone

import pytest
import typer
from typer.main import get_command

from app import cli as cli_module
from app.models import Chamber, FeedItem, PartyLane, RunResult, SourceConfig


def make_source(enabled: bool = True) -> SourceConfig:
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
        parser="parser",
        enabled=enabled,
    )


def make_item() -> FeedItem:
    seen = datetime(2026, 7, 20, tzinfo=timezone.utc)
    return FeedItem(
        source_id="source",
        source_name="Source",
        committee="Committee",
        chamber=Chamber.house,
        party_lane=PartyLane.majority,
        title="Release",
        url="https://example.com/release",
        published_at=seen,
        first_seen_at=seen,
        last_seen_at=seen,
    )


def test_cli_keeps_all_command_names():
    commands = get_command(cli_module.cli).commands

    assert set(commands) == {"run", "test-source", "render", "list-sources"}


def test_run_command_executes_pipeline(monkeypatch):
    calls = []

    async def fake_pipeline():
        calls.append("run")

    monkeypatch.setattr(cli_module, "run_pipeline", fake_pipeline)

    cli_module.run()

    assert calls == ["run"]


def test_render_command_uses_saved_state_and_all_source_lists(tmp_path, monkeypatch):
    item = make_item()
    source = make_source()
    calls = []
    monkeypatch.setattr(cli_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(cli_module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(cli_module, "SITE_DIR", tmp_path / "site")
    monkeypatch.setattr(cli_module, "load_state", lambda _data_dir: {"source": [item]})
    monkeypatch.setattr(cli_module, "get_enabled_sources", lambda: [source])
    monkeypatch.setattr(cli_module, "load_sources", lambda: [source])
    monkeypatch.setattr(
        cli_module,
        "render_site",
        lambda items, summary, output_dir, **kwargs: calls.append(
            (items, summary, output_dir, kwargs)
        ),
    )

    cli_module.render()

    assert calls[0][0] == [item]
    assert calls[0][1] is None
    assert calls[0][2] == tmp_path / "site"
    assert calls[0][3]["sources_config"] == [source]
    assert calls[0][3]["all_sources_config"] == [source]


def test_list_sources_hides_disabled_sources_by_default(monkeypatch, capsys):
    enabled = make_source()
    disabled = make_source(enabled=False).model_copy(
        update={"id": "planned", "name": "Planned"}
    )
    monkeypatch.setattr(cli_module, "load_sources", lambda: [enabled, disabled])

    cli_module.list_sources()
    enabled_only = capsys.readouterr().out
    cli_module.list_sources(enabled_only=False)
    all_sources = capsys.readouterr().out

    assert "[ON] source: Source" in enabled_only
    assert "Planned" not in enabled_only
    assert "[OFF] planned: Planned" in all_sources


def test_test_source_command_prints_items_and_exits_on_failure(monkeypatch, capsys):
    source = make_source()
    item = make_item()

    class ClientContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, _exc_type, _exc, _traceback):
            return False

    async def success(_source, _client):
        return [
            item
        ], RunResult(
            source_id=source.id,
            source_name=source.name,
            items_found=1,
            fetch_duration_ms=12,
        )

    monkeypatch.setattr(cli_module, "get_source_by_id", lambda _source_id: source)
    monkeypatch.setattr(cli_module, "create_client", ClientContext)
    monkeypatch.setattr(cli_module, "process_source", success)

    cli_module.test_source("source")

    assert "[2026-07-20] Release" in capsys.readouterr().out

    async def failure(_source, _client):
        return [], RunResult(
            source_id=source.id,
            source_name=source.name,
            success=False,
            errors=["Fetch failed: test"],
        )

    monkeypatch.setattr(cli_module, "process_source", failure)
    with pytest.raises(typer.Exit) as error:
        cli_module.test_source("source")
    assert error.value.exit_code == 1
