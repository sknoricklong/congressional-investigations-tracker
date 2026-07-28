"""Parser for Senate Judiciary Committee press pages.

Covers:
- judiciary.senate.gov/press/majority
- judiciary.senate.gov/press/minority

Structure: Container divs with p.Heading--time for date, sibling a > h3 for title.
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from app.models import FeedItem, SourceConfig
from app.parsers import register
from app.utils import canonicalize_url, clean_text, is_pdf_url, parse_date


@register("senate_judiciary_press")
def parse_senate_judiciary_press(html: str, source: SourceConfig) -> list[FeedItem]:
    """Senate Judiciary: p.Heading--time for date, nearby a with h3 for title."""
    soup = BeautifulSoup(html, "lxml")
    items: list[FeedItem] = []

    for date_el in soup.select("p.Heading--time"):
        date_text = date_el.get_text().strip()
        date = parse_date(date_text)

        # Find the link in the same container (parent or grandparent div)
        container = date_el.parent
        if not container:
            continue

        # Look up to 2 levels for a link with /press/ in href
        link = None
        for _ in range(3):
            link = container.select_one("a[href*='/press/']")
            if link:
                break
            if container.parent:
                container = container.parent
            else:
                break

        if not link:
            continue

        href = str(link.get("href", ""))
        if not href:
            continue

        url = canonicalize_url(href, source.url)

        # Title from h3 inside link, or link text
        h3 = link.select_one("h3")
        title = clean_text(h3.get_text()) if h3 else clean_text(link.get_text())
        if not title:
            continue

        # Summary from p inside link (not the date p)
        summary = ""
        for p in link.select("p"):
            if "Heading--time" not in " ".join(p.get("class", [])):
                text = clean_text(p.get_text())
                if text and len(text) > 20:
                    summary = text[:300]
                    break

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
