"""Parsers for pages using .post / a.news-post card layouts.

Covers:
- oversight.house.gov/release/ and /letter/ (.post > a > .excerpt > .title, time, p)
- homeland.house.gov/press/ (a.news-post > div.date + div.title)
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from app.models import FeedItem, SourceConfig
from app.parsers import register
from app.utils import canonicalize_url, clean_text, is_pdf_url, parse_date


def _parse_post_cards(html: str, source: SourceConfig) -> list[FeedItem]:
    """Parser for pages using .post card layout (oversight.house.gov)."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for post in soup.select(".post"):
        link_tag = post.select_one("a")
        if not link_tag:
            continue

        href = link_tag.get("href", "")
        if not href:
            continue

        url = canonicalize_url(str(href), source.url)

        title_tag = post.select_one(".title")
        title = clean_text(title_tag.get_text()) if title_tag else ""
        if not title:
            continue

        time_tag = post.select_one("time")
        date = None
        if time_tag:
            date = parse_date(time_tag.get("datetime", "")) or parse_date(time_tag.get_text())

        summary = ""
        excerpt = post.select_one(".excerpt")
        if excerpt:
            p_tag = excerpt.select_one("p")
            if p_tag:
                summary = clean_text(p_tag.get_text())

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


def _parse_news_post_links(html: str, source: SourceConfig) -> list[FeedItem]:
    """Parser for a.news-post > div.date + div.title (homeland.house.gov/press/)."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for link in soup.select("a.news-post"):
        href = link.get("href", "")
        if not href:
            continue

        url = canonicalize_url(str(href), source.url)

        title_div = link.select_one("div.title")
        title = clean_text(title_div.get_text()) if title_div else ""
        if not title:
            continue

        date_div = link.select_one("div.date")
        date = parse_date(date_div.get_text()) if date_div else None

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


@register("oversight_house_press")
def parse_oversight_press(html: str, source: SourceConfig) -> list[FeedItem]:
    return _parse_post_cards(html, source)


@register("oversight_house_letters")
def parse_oversight_letters(html: str, source: SourceConfig) -> list[FeedItem]:
    return _parse_post_cards(html, source)


@register("homeland_house_press")
def parse_homeland_press(html: str, source: SourceConfig) -> list[FeedItem]:
    return _parse_news_post_links(html, source)
