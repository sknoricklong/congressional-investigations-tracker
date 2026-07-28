from __future__ import annotations

import asyncio
import json
import logging

import typer

from app.config import (
    DATA_DIR,
    LOGS_DIR,
    SITE_DIR,
    get_enabled_sources,
    get_source_by_id,
    load_sources,
)
from app.diff import load_state
from app.fetch import create_client
from app.models import RunSummary
from app.pipeline import process_source, run_pipeline
from app.render import render_site

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

cli = typer.Typer(name="congress-monitor", help="Congressional committee update monitor.")


@cli.command()
def run() -> None:
    """Run the full pipeline: fetch, diff, render."""
    asyncio.run(run_pipeline())


@cli.command()
def test_source(source_id: str) -> None:
    """Fetch and parse a single source for debugging."""

    async def _test() -> None:
        source = get_source_by_id(source_id)
        logger.info(f"Testing source: {source.id} ({source.url})")

        async with create_client() as client:
            items, result = await process_source(source, client)

        if not result.success:
            logger.error(f"Failed: {'; '.join(result.errors)}")
            raise typer.Exit(1)

        logger.info(f"Found {len(items)} items in {result.fetch_duration_ms:.0f}ms")
        for item in items[:10]:
            date = (
                item.published_at.strftime("%Y-%m-%d")
                if item.published_at
                else "no date"
            )
            print(f"  [{date}] {item.title[:80]}")
            print(f"    {item.url}")

    asyncio.run(_test())


@cli.command()
def render() -> None:
    """Re-render the site from existing state without fetching."""
    state = load_state(DATA_DIR)
    all_items = [item for items in state.values() for item in items]

    summary = None
    run_log = LOGS_DIR / "last_run.json"
    if run_log.exists():
        try:
            summary = RunSummary(**json.loads(run_log.read_text()))
        except Exception:
            pass

    sources = get_enabled_sources()
    render_site(
        all_items,
        summary,
        SITE_DIR,
        sources_config=sources,
        all_sources_config=load_sources(),
    )
    logger.info(f"Rendered {len(all_items)} items to {SITE_DIR / 'index.html'}")


@cli.command()
def list_sources(enabled_only: bool = True) -> None:
    """List configured sources."""
    sources = load_sources()
    for source in sources:
        if enabled_only and not source.enabled:
            continue
        status = "ON" if source.enabled else "OFF"
        print(f"  [{status}] {source.id}: {source.name} ({source.tier.value})")
        print(f"         {source.url}")


app = cli

if __name__ == "__main__":
    cli()
