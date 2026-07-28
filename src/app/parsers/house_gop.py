"""Parsers for House GOP majority committee pages.

Covers:
- judiciary.house.gov/media/press-releases (Drupal .evo-view-wrapper with .evo-press-release__body)
- judiciary.house.gov/documents/letters (li > a to PDF links)
- energycommerce.house.gov/news/press-release (article.shadow-md with h3 + a.mt-auto)
- energycommerce.house.gov/news/letter (same article layout)
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.models import FeedItem, SourceConfig
from app.parsers import register
from app.utils import canonicalize_url, clean_text, is_pdf_url, parse_date


@register("judiciary_house_press")
def parse_judiciary_house_press(html: str, source: SourceConfig) -> list[FeedItem]:
    """Drupal views-row: .h3 for title, .col-auto for date, .evo-read-more a for link."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    # Container holds all press release rows
    container = soup.select_one(".evo-views-row-container, .evo-view-wrapper")
    if not container:
        return items

    for row in container.select(".views-row"):
        # Title from .h3 div
        title_el = row.select_one(".h3")
        if not title_el:
            continue
        title = clean_text(title_el.get_text())
        if not title:
            continue

        # Link from "Read More" button
        link = row.select_one(".evo-read-more a, a.btn")
        if not link:
            continue
        href = str(link.get("href", ""))
        if not href:
            continue
        url = canonicalize_url(href, source.url)

        # Date from first .col-auto (contains "April 1, 2026")
        date = None
        for col in row.select(".col-auto"):
            parsed = parse_date(col.get_text().strip())
            if parsed:
                date = parsed
                break

        # Summary from .evo-press-release__body first paragraph
        summary = ""
        body = row.select_one(".evo-press-release__body")
        if body:
            p = body.select_one("p")
            if p:
                summary = clean_text(p.get_text())[:300]

        items.append(FeedItem(
            source_id=source.id,
            source_name=source.name,
            committee=source.committee,
            chamber=source.chamber,
            party_lane=source.party_lane,
            title=title,
            url=url,
            published_at=date,
            summary=summary,
            item_type=source.kind,
            is_pdf=is_pdf_url(url),
            source_tier=source.tier,
        ))

        if len(items) >= source.recent_item_limit:
            break

    return items


@register("judiciary_house_letters")
def parse_judiciary_house_letters(html: str, source: SourceConfig) -> list[FeedItem]:
    """li > a pointing to PDF files on judiciary.house.gov."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    # Find the main content area
    content = soup.select_one(".field--name-body, .evo-page-content, main, article")
    if not content:
        content = soup

    for li in content.select("li"):
        link = li.select_one("a")
        if not link:
            continue

        href = str(link.get("href", ""))
        if not href:
            continue

        title = clean_text(link.get_text())
        if not title or len(title) < 10:
            continue

        url = canonicalize_url(href, source.url)

        # Extract date from title and strip it. Formats: "3.13.25" at end, or "January 15, 2025"
        date = None
        # Try M.D.YY at end of title (most common for judiciary letters)
        date_match = re.search(r"\s*(\d{1,2}\.\d{1,2}\.\d{2})\s*$", title)
        if date_match:
            date = parse_date(date_match.group(1))
            title = title[:date_match.start()].strip()
        # Fall back to full month name
        if not date:
            date_match = re.search(
                r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
                r"\s+\d{1,2},?\s+\d{4}",
                title,
            )
            if date_match:
                date = parse_date(date_match.group())

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

    items.sort(key=lambda x: x.published_at.isoformat() if x.published_at else "", reverse=True)
    return items[:source.recent_item_limit]


def _parse_energy_commerce_articles(html: str, source: SourceConfig) -> list[FeedItem]:
    """Shared parser for energycommerce.house.gov article cards.

    Structure: article.shadow-md > h3.brand-font + p + a.mt-auto[href=/posts/...]
    """
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for article in soup.select("article"):
        # Title from h3
        h3 = article.select_one("h3")
        if not h3:
            continue

        title = clean_text(h3.get_text())
        if not title:
            continue

        # Link from a.mt-auto ("See More" link) which has the real URL
        see_more = article.select_one("a.mt-auto")
        if see_more:
            href = str(see_more.get("href", ""))
        else:
            # Fallback: any a with /posts/ in href
            link = article.select_one("a[href*='/posts/']")
            href = str(link.get("href", "")) if link else ""

        if not href:
            continue

        url = canonicalize_url(href, source.url)

        # Summary from first p after h3
        summary = ""
        first_p = article.select_one("p")
        if first_p:
            summary = clean_text(first_p.get_text())[:300]

        # Date: try to extract from summary text
        date = None
        date_match = re.search(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
            r"\s+\d{1,2},?\s+\d{4}",
            summary,
        )
        if date_match:
            date = parse_date(date_match.group())

        items.append(FeedItem(
            source_id=source.id,
            source_name=source.name,
            committee=source.committee,
            chamber=source.chamber,
            party_lane=source.party_lane,
            title=title,
            url=url,
            published_at=date,
            summary=summary,
            item_type=source.kind,
            is_pdf=is_pdf_url(url),
            source_tier=source.tier,
        ))

        if len(items) >= source.recent_item_limit:
            break

    return items


@register("energy_commerce_press")
def parse_energy_commerce_press(html: str, source: SourceConfig) -> list[FeedItem]:
    return _parse_energy_commerce_articles(html, source)


@register("energy_commerce_letters")
def parse_energy_commerce_letters(html: str, source: SourceConfig) -> list[FeedItem]:
    return _parse_energy_commerce_articles(html, source)
