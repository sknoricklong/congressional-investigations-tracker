from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from app.models import FeedItem, RunSummary, SourceConfig

TEMPLATES_DIR = Path(__file__).parent / "templates"
ET = ZoneInfo("America/New_York")


def render_site(
    items: list[FeedItem],
    summary: RunSummary | None,
    output_dir: Path,
    sources_config: list[SourceConfig] | None = None,
    all_sources_config: list[SourceConfig] | None = None,
) -> None:
    """Render site/index.html and site/feed.json."""
    output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
    )

    now_et = datetime.now(ET)

    # Collect unique values for filter checkboxes
    committees = sorted({i.committee for i in items})
    chambers = sorted({i.chamber.value for i in items})
    party_lanes = sorted({i.party_lane.value for i in items})
    item_types = sorted({i.item_type.value for i in items})
    sources = sorted({i.source_name for i in items})

    # Build source URL and coverage maps for the Sources tab
    source_urls = {}
    source_covers = {}
    if sources_config:
        source_urls = {s.name: s.url for s in sources_config}
        source_covers = {s.name: s.why_relevant for s in sources_config if s.why_relevant}

    # Disabled sources appear on the Sources tab as planned coverage, so the
    # registry shows the full intended source list honestly.
    planned_sources = [s for s in (all_sources_config or []) if not s.enabled]

    # Count items published in last 24h per source (by publication date, not diff status)
    now_utc = datetime.now(timezone.utc)
    cutoff_24h = now_utc - timedelta(hours=24)
    recent_by_source: dict[str, int] = {}
    for item in items:
        if item.published_at and item.published_at >= cutoff_24h:
            recent_by_source[item.source_name] = recent_by_source.get(item.source_name, 0) + 1
    total_recent_24h = sum(recent_by_source.values())

    # Items without a source-scraped summary show no summary anywhere: the row
    # meta line already carries committee/lane/type, and a generated
    # restatement of the title adds nothing. The flag keeps the email contract:
    # summary_generated=false means the text came from the source.
    generated_summary_ids: set[str] = set()
    for item in items:
        if not item.summary or not item.summary.strip():
            generated_summary_ids.add(item.item_id)

    # Deduplicate items with the same URL (keep first occurrence, which has earlier source priority)
    seen_urls: set[str] = set()
    deduped: list[FeedItem] = []
    for item in items:
        if item.url not in seen_urls:
            seen_urls.add(item.url)
            deduped.append(item)
    items = deduped

    # Sort all items by date descending (newest first)
    items = sorted(items, key=lambda x: x.published_at or x.first_seen_at, reverse=True)

    template = env.get_template("index.html.j2")
    html = template.render(
        all_items=items,
        last_updated=now_et,
        current_year=now_et.year,
        summary=summary,
        committees=committees,
        chambers=chambers,
        party_lanes=party_lanes,
        item_types=item_types,
        sources=sources,
        source_urls=source_urls,
        source_covers=source_covers,
        recent_by_source=recent_by_source,
        total_recent_24h=total_recent_24h,
        planned_sources=planned_sources,
    )
    (output_dir / "index.html").write_text(html)

    # JSON feed
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": "Congressional Investigations Monitor",
        "home_page_url": "https://your-deployment.vercel.app",
        "feed_url": "https://your-deployment.vercel.app/feed.json",
        "items": [
            {
                "id": item.item_id,
                "title": item.title,
                "url": item.url,
                "date_published": item.published_at.isoformat() if item.published_at else None,
                "summary": item.summary,
                "tags": [item.committee, item.chamber.value, item.item_type.value],
                "_congress_monitor": {
                    "source_id": item.source_id,
                    "source_name": item.source_name,
                    "party_lane": item.party_lane.value,
                    "status": item.status.value,
                    "is_pdf": item.is_pdf,
                    "first_seen_at": item.first_seen_at.isoformat(),
                    "cluster_id": item.cluster_id,
                    "summary_generated": item.item_id in generated_summary_ids,
                },
            }
            for item in items
        ],
    }
    (output_dir / "feed.json").write_text(json.dumps(feed, indent=2, default=str))
