"""Parsers for Drupal-based committee pages.

Covers:
- democrats-judiciary.house.gov/media-center/press-releases (.views-row .evo-media-object)
- democrats-judiciary.house.gov/letters (article content links)
- democrats-homeland.house.gov/news/correspondence (span.date + h2.title + p.summary)
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.models import FeedItem, SourceConfig
from app.parsers import register
from app.utils import canonicalize_url, clean_text, is_pdf_url, parse_date


@register("judiciary_dems_press")
def parse_judiciary_dems_press(html: str, source: SourceConfig) -> list[FeedItem]:
    """Drupal views-row with .evo-media-object containing .h5 > a for title, .col-auto for date."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for row in soup.select(".views-row"):
        # Title: .h5 > a or .media-body .h5 a
        title_el = row.select_one(".h5 a, .media-body a")
        if not title_el:
            continue

        title = clean_text(title_el.get_text())
        if not title:
            continue

        href = str(title_el.get("href", ""))
        if not href:
            continue

        url = canonicalize_url(href, source.url)

        # Date: .col-auto containing date text (first one)
        date = None
        for col in row.select(".col-auto"):
            text = col.get_text().strip()
            parsed = parse_date(text)
            if parsed:
                date = parsed
                break

        # Summary: .evo-press-release__body first paragraph
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


@register("judiciary_dems_letters")
def parse_judiciary_dems_letters(html: str, source: SourceConfig) -> list[FeedItem]:
    """Judiciary dems letters page. Links with /letters/ in href, sometimes grouped by session."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    # Look for any links pointing to /letters/ paths
    for a in soup.select("a[href*='/letters/']"):
        href = str(a.get("href", ""))
        title = clean_text(a.get_text())

        # Skip navigation links
        if not title or title.lower() in ("letters", "back", "next", "previous"):
            continue
        if len(title) < 10:
            continue

        url = canonicalize_url(href, source.url)

        # Try to find date near the link
        date = None
        parent = a.parent
        if parent:
            text = parent.get_text()
            # Look for date patterns in surrounding text
            import re
            date_match = re.search(
                r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
                r"\s+\d{1,2},?\s+\d{4}",
                text,
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

        if len(items) >= source.recent_item_limit:
            break

    return items


@register("homeland_dems_correspondence")
def parse_homeland_dems_correspondence(html: str, source: SourceConfig) -> list[FeedItem]:
    """span.date.black + h2.title > a + p.summary, separated by <hr>."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    # Each item has: span.date > h2.title > p.summary > hr
    for h2 in soup.select("h2.title"):
        title_link = h2.select_one("a")
        if title_link:
            title = clean_text(title_link.get_text())
            href = str(title_link.get("href", ""))
        else:
            title = clean_text(h2.get_text())
            href = ""

        if not title:
            continue

        url = canonicalize_url(href, source.url) if href else ""
        if not url:
            continue

        # Date from preceding span.date
        date = None
        prev = h2.find_previous_sibling("span", class_="date")
        if prev:
            date = parse_date(prev.get_text())

        # Summary from following p.summary
        summary = ""
        next_p = h2.find_next_sibling("p", class_="summary")
        if next_p:
            summary = clean_text(next_p.get_text())
            # The excerpt ends with navigation text ("To view the letter...,
            # click here. Continue Reading"); it is not release content.
            summary = re.sub(
                r"\s*To view[^.]*?click[^.]*?[.…]*\s*(?:Continue Reading)?\s*$",
                "", summary, flags=re.IGNORECASE,
            )
            summary = re.sub(
                r"\s*[.…]*\s*Continue Reading\s*$", "", summary, flags=re.IGNORECASE,
            ).strip()[:300]

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
