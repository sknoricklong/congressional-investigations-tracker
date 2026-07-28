"""Parsers for table and flat-list layouts.

Covers:
- oversightdemocrats.house.gov/news/press-releases (tr > td.date + td > a)
- oversightdemocrats.house.gov/letters (tr > td date + td type + td > a)
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from app.models import FeedItem, SourceConfig
from app.parsers import register
from app.utils import canonicalize_url, clean_text, is_pdf_url, parse_date


@register("oversight_dems_press")
def parse_oversight_dems_press(html: str, source: SourceConfig) -> list[FeedItem]:
    """oversightdemocrats press: tr > td.date + td > a."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for tr in soup.select("tr"):
        date_td = tr.select_one("td.date")
        if not date_td:
            continue

        # Title and link in the other td
        other_tds = [td for td in tr.select("td") if td != date_td]
        link = None
        for td in other_tds:
            a = td.select_one("a")
            if a and a.get("href", ""):
                link = a
                break

        if not link:
            continue

        href = str(link.get("href", "")).strip()
        if not href:
            continue

        url = canonicalize_url(href, source.url)
        title = clean_text(link.get_text())
        if not title:
            continue

        date = parse_date(date_td.get_text())

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


@register("oversight_dems_letters")
def parse_oversight_dems_letters(html: str, source: SourceConfig) -> list[FeedItem]:
    """oversightdemocrats letters: tr > td(date) + td(type) + td > a (download link)."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for tr in soup.select("tr"):
        tds = tr.select("td")
        if len(tds) < 3:
            continue

        date_text = tds[0].get_text().strip()
        # letter_type = tds[1].get_text().strip()  # "Letter", "Joint Letter"
        recipient_td = tds[2]
        link = recipient_td.select_one("a")

        if not link:
            continue

        href = str(link.get("href", "")).strip()
        if not href:
            continue

        url = canonicalize_url(href, source.url)
        title = clean_text(link.get_text())
        if not title:
            continue

        date = parse_date(date_text)

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
