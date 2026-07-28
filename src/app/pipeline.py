from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

import app.parsers.date_link_list  # noqa: F401
import app.parsers.drupal_node  # noqa: F401
import app.parsers.house_gop  # noqa: F401
import app.parsers.post_list  # noqa: F401
import app.parsers.senate_hsgac  # noqa: F401
import app.parsers.senate_press  # noqa: F401
from app.config import DATA_DIR, LOGS_DIR, SITE_DIR, get_enabled_sources, load_sources
from app.diff import append_history, diff_items, load_state, save_state
from app.fetch import create_client, fetch_page, fetch_source
from app.models import FeedItem, RunResult, RunSummary
from app.normalize import normalize_items
from app.parsers import get_parser
from app.render import render_site
from app.utils import clean_text, parse_date

STALENESS_THRESHOLD_DAYS = 5

# Keep the current logger name so the command output does not change.
logger = logging.getLogger("app.cli")


async def process_source(source, client) -> tuple[list[FeedItem], RunResult]:
    """Fetch, parse, and normalize a single source. Returns (items, result)."""
    start = time.monotonic()
    result = RunResult(source_id=source.id, source_name=source.name)

    try:
        parser = get_parser(source.parser)
    except KeyError as e:
        result.success = False
        result.errors.append(str(e))
        return [], result

    try:
        pages = await fetch_source(source, client)
    except Exception as e:
        result.success = False
        result.errors.append(f"Fetch failed: {e}")
        result.fetch_duration_ms = (time.monotonic() - start) * 1000
        return [], result

    items: list[FeedItem] = []
    for html in pages:
        try:
            parsed = parser(html, source)
            items.extend(parsed)
        except Exception as e:
            result.success = False
            result.errors.append(f"Parse error: {e}")
            _save_debug_fixture(source.id, html)

    items_needing_dates = [item for item in items if item.published_at is None and item.url]
    if items_needing_dates:
        for item in items_needing_dates:
            try:
                detail_html = await fetch_page(item.url, client)
                date = _extract_date_from_detail(detail_html)
                if date:
                    item = item.model_copy(update={"published_at": date})
                    for index, original in enumerate(items):
                        if original.url == item.url:
                            items[index] = item
                            break
            except Exception:
                pass

    truncated = [item for item in items if item.title.rstrip().endswith(("...", "…"))]
    for item in truncated:
        try:
            detail_html = await fetch_page(item.url, client)
            full_title = _extract_title_from_detail(detail_html)
            if full_title and _same_title_stem(item.title, full_title):
                fixed = item.model_copy(update={"title": full_title})
                for index, original in enumerate(items):
                    if original.url == item.url:
                        items[index] = fixed
                        break
        except Exception:
            pass

    items = normalize_items(items)
    result.items_found = len(items)
    result.fetch_duration_ms = (time.monotonic() - start) * 1000
    return items, result


def _extract_date_from_detail(html: str):
    """Try to extract a date from a detail or article page."""
    max_plausible = datetime.now(timezone.utc) + timedelta(days=1)

    def _plausible(date):
        if date is None:
            return None
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date if date <= max_plausible else None

    soup = BeautifulSoup(html, "lxml")

    for time_tag in soup.select("time"):
        date_text = time_tag.get("datetime", "")
        if date_text:
            date = _plausible(parse_date(date_text))
            if date:
                return date
        date = _plausible(parse_date(time_tag.get_text()))
        if date:
            return date

    for meta in soup.select("meta[property*='time'], meta[name*='date'], meta[property*='date']"):
        date = _plausible(parse_date(meta.get("content", "")))
        if date:
            return date

    for element in soup.select("h1, h2, .date, [class*='date']"):
        sibling = element.find_next_sibling()
        if sibling:
            text = sibling.get_text().strip()[:60]
            match = re.search(
                r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
                r"\w*\s+\d{1,2},?\s+\d{4}",
                text,
            )
            if match:
                date = _plausible(parse_date(match.group()))
                if date:
                    return date

    text = soup.get_text()
    match = re.search(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\w*\s+\d{1,2},\s+\d{4})",
        text,
    )
    if match:
        date = _plausible(parse_date(match.group(1)))
        if date:
            return date

    return None


def _same_title_stem(truncated_title: str, full_title: str) -> bool:
    """Check whether a detail headline continues a truncated listing title."""

    def normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    stem = normalize(truncated_title)[:20]
    return bool(stem) and normalize(full_title).startswith(stem)


def _extract_title_from_detail(html: str) -> str | None:
    """Read the full headline from h1 first, then og:title."""
    soup = BeautifulSoup(html, "lxml")

    heading = soup.select_one("h1")
    if heading:
        text = clean_text(heading.get_text())
        if text:
            return text

    meta = soup.select_one("meta[property='og:title']")
    if meta:
        text = clean_text(str(meta.get("content", "")))
        text = re.sub(r"\s*[|\-–]\s*[^|\-–]{0,80}$", "", text).strip() or text
        if text:
            return text

    return None


def _save_debug_fixture(source_id: str, html: str) -> None:
    """Save HTML to logs for debugging parse failures."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOGS_DIR / f"debug_{source_id}_{timestamp}.html"
    path.write_text(html)
    logger.info(f"Saved debug fixture to {path}")


async def run_pipeline() -> None:
    """Fetch all enabled sources, compare them, save them, and render the site."""
    started_at = datetime.now(timezone.utc)
    sources = get_enabled_sources()
    logger.info(f"Processing {len(sources)} enabled sources")

    previous_state = load_state(DATA_DIR)
    current_state: dict[str, list[FeedItem]] = {}
    all_items: list[FeedItem] = []
    results: list[RunResult] = []

    async with create_client() as client:
        for source in sources:
            logger.info(f"  {source.id}: {source.url}")
            items, result = await process_source(source, client)

            previous_items = previous_state.get(source.id, [])
            diffed = diff_items(items, previous_items)

            result.new_count = sum(1 for item in diffed if item.status.value == "new")
            result.updated_count = sum(1 for item in diffed if item.status.value == "updated")
            result.unchanged_count = sum(
                1 for item in diffed if item.status.value == "unchanged"
            )

            current_state[source.id] = diffed
            all_items.extend(diffed)
            results.append(result)

            if result.success:
                logger.info(
                    f"    Found {result.items_found} items: "
                    f"{result.new_count} new, {result.updated_count} updated, "
                    f"{result.unchanged_count} unchanged"
                )
            else:
                logger.warning(f"    Failed: {'; '.join(result.errors)}")

    finished_at = datetime.now(timezone.utc)
    summary = RunSummary(
        started_at=started_at,
        finished_at=finished_at,
        sources_attempted=len(sources),
        sources_succeeded=sum(1 for result in results if result.success),
        sources_failed=sum(1 for result in results if not result.success),
        total_new=sum(result.new_count for result in results),
        total_updated=sum(result.updated_count for result in results),
        results=results,
    )

    health_warnings = check_health(current_state, previous_state)
    has_regression = any(warning.startswith("REGRESSION") for warning in health_warnings)

    if health_warnings:
        for warning in health_warnings:
            if warning.startswith("REGRESSION"):
                logger.error(f"HEALTH: {warning}")
            else:
                logger.warning(f"HEALTH: {warning}")

    if has_regression:
        logger.error(
            "Skipping state save due to regression. "
            "Previous state preserved. Rendering from previous state."
        )
        previous_items = [
            item for source_items in previous_state.values() for item in source_items
        ]
        render_site(
            previous_items,
            summary,
            SITE_DIR,
            sources_config=sources,
            all_sources_config=load_sources(),
        )
    else:
        save_state(current_state, DATA_DIR)
        append_history(all_items, DATA_DIR)
        render_site(
            all_items,
            summary,
            SITE_DIR,
            sources_config=sources,
            all_sources_config=load_sources(),
        )

    _save_run_log(summary, health_warnings)

    logger.info(
        f"Done. {summary.total_new} new, {summary.total_updated} updated. "
        f"{summary.sources_failed} failures. Output: {SITE_DIR / 'index.html'}"
    )

    if has_regression:
        raise SystemExit(1)


def check_health(
    current_state: dict[str, list[FeedItem]],
    previous_state: dict[str, list[FeedItem]],
) -> list[str]:
    """Find stale sources and collection regressions."""
    now = datetime.now(timezone.utc)
    warnings: list[str] = []

    for source_id, items in current_state.items():
        if not items:
            warnings.append(f"REGRESSION {source_id}: returned 0 items")
            continue

        dated = [item for item in items if item.published_at]
        newest = max(item.published_at for item in dated) if dated else None

        if newest:
            age = now - newest
            if age > timedelta(days=STALENESS_THRESHOLD_DAYS):
                warnings.append(
                    f"STALE {source_id}: newest item is {age.days}d old "
                    f"({newest.strftime('%Y-%m-%d')})"
                )

        previous_items = previous_state.get(source_id, [])
        if previous_items:
            previous_dated = [item for item in previous_items if item.published_at]
            previous_newest = (
                max(item.published_at for item in previous_dated)
                if previous_dated
                else None
            )

            if newest and previous_newest and newest < previous_newest:
                warnings.append(
                    f"REGRESSION {source_id}: newest date went from "
                    f"{previous_newest.strftime('%Y-%m-%d')} to "
                    f"{newest.strftime('%Y-%m-%d')}"
                )

            if len(items) < len(previous_items):
                warnings.append(
                    f"REGRESSION {source_id}: item count dropped from "
                    f"{len(previous_items)} to {len(items)}"
                )

    return warnings


def _save_run_log(summary: RunSummary, health_warnings: list[str] | None = None) -> None:
    """Save the run summary to logs/last_run.json."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / "last_run.json"
    data = summary.model_dump(mode="json")
    if health_warnings:
        data["health_warnings"] = health_warnings
    path.write_text(json.dumps(data, indent=2, default=str))
