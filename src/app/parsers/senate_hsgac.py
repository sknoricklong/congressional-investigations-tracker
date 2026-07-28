"""Parsers for Senate HSGAC and PSI pages (Elementor/JET Engine).

Covers:
- hsgac.senate.gov/media/majority-news/ and minority-news/
  (.jet-listing-grid__item with .sen-listing-month, .sen-listing-day texts,
   h5.jet-listing-dynamic-field__content for title,
   a.jet-engine-listing-overlay-link for URL)
- hsgac.senate.gov/subcommittees/investigations/library/
  (.jet-listing-grid__item with .sen-news-item-date for date,
   h3.jet-listing-dynamic-field__content for title,
   a.jet-engine-listing-overlay-link for URL)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from app.models import FeedItem, PartyLane, SourceConfig
from app.parsers import register
from app.utils import canonicalize_url, clean_text, is_pdf_url, parse_date


def _infer_year(month_str: str, day_str: str) -> datetime | None:
    """Parse month and day, using the prior year when the date is in the future."""
    now = datetime.now(timezone.utc)
    date = parse_date(f"{month_str} {day_str}, {now.year}")
    if date and date > now:
        date = parse_date(f"{month_str} {day_str}, {now.year - 1}")
    return date


@register("hsgac_news")
def parse_hsgac_news(html: str, source: SourceConfig) -> list[FeedItem]:
    """HSGAC news: .jet-listing-grid__item with month/day divs and overlay link."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for item_div in soup.select(".jet-listing-grid__item"):
        # URL from overlay link
        link = item_div.select_one("a.jet-engine-listing-overlay-link")
        if not link:
            continue

        href = str(link.get("href", ""))
        if not href:
            continue

        url = canonicalize_url(href, source.url)

        # Title from h5 (jet-listing-dynamic-field__content)
        h5 = item_div.select_one("h5")
        if not h5:
            continue

        title = clean_text(h5.get_text())
        # Strip trailing arrow characters (various unicode arrows)
        title = re.sub(r"[\s\u2190-\u21FF\u2794\u279C\u279E→>➞]+$", "", title)
        if not title:
            continue

        # Date from .sen-listing-month and .sen-listing-day text content
        # These are direct text inside divs, not spans
        date = None
        month_el = item_div.select_one(
            "[class*='sen-listing-month']:not([class*='elementor-hidden'])"
        )
        day_el = item_div.select_one(
            "[class*='sen-listing-day']:not([class*='elementor-hidden'])"
        )

        if month_el and day_el:
            month = month_el.get_text().strip()
            day = day_el.get_text().strip()
            # These pages don't show year in the visible elements
            # Infer current year
            if month and day:
                date = _infer_year(month, day)

        items.append(FeedItem(
            source_id=source.id,
            source_name=source.name,
            committee=source.committee,
            chamber=source.chamber,
            party_lane=source.party_lane,
            title=title,
            url=url,
            published_at=date,
            item_type=source.kind,
            is_pdf=is_pdf_url(url),
            source_tier=source.tier,
        ))

        if len(items) >= source.recent_item_limit:
            break

    return items


@register("psi_library")
def parse_psi_library(html: str, source: SourceConfig) -> list[FeedItem]:
    """PSI library: .jet-listing-grid__item with .sen-news-item-date and h3 title."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for item_div in soup.select(".jet-listing-grid__item"):
        # URL from overlay link
        link = item_div.select_one("a.jet-engine-listing-overlay-link")
        if not link:
            continue

        href = str(link.get("href", ""))
        if not href:
            continue

        url = canonicalize_url(href, source.url)

        # Title from h3
        h3 = item_div.select_one("h3")
        if not h3:
            continue

        title = clean_text(h3.get_text())
        if not title:
            continue

        # Date from .sen-news-item-date or span with date class
        date = None
        date_el = item_div.select_one("[class*='sen-news-item-date'] span, [class*='date'] span")
        if date_el:
            date = parse_date(date_el.get_text().strip())

        # The library holds documents from both parties. Titles name the
        # signers ("Letter from Ranking Members...", "Chairman... Releases"),
        # so derive the lane from the title; fall back to the configured lane.
        title_lower = title.lower()
        if "ranking member" in title_lower:
            lane = PartyLane.minority
        elif (
            "chairman" in title_lower
            or "chairwoman" in title_lower
            or title_lower.startswith("chair ")
        ):
            lane = PartyLane.majority
        else:
            lane = source.party_lane

        items.append(FeedItem(
            source_id=source.id,
            source_name=source.name,
            committee=source.committee,
            chamber=source.chamber,
            party_lane=lane,
            title=title,
            url=url,
            published_at=date,
            item_type=source.kind,
            is_pdf=is_pdf_url(url),
            source_tier=source.tier,
        ))

        if len(items) >= source.recent_item_limit:
            break

    return items
