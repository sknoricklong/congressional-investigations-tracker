from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

# Tracking parameters to strip from URLs
_TRACKING_PARAMS = {
    "_ga",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonicalize_url(url: str, base_url: str = "") -> str:
    """Normalize a URL: resolve relative paths, strip tracking params, lowercase scheme/host."""
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlparse(url)

    # Strip tracking params
    if parsed.query:
        params = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = {k: v for k, v in params.items() if k not in _TRACKING_PARAMS}
        query = urlencode(cleaned, doseq=True)
    else:
        query = ""

    # Normalize: lowercase scheme and host, strip trailing slash from path
    path = parsed.path.rstrip("/") if parsed.path != "/" else "/"

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.params,
        query,
        "",  # drop fragment
    ))


def parse_date(text: str | None) -> datetime | None:
    """Parse a date string in various congressional page formats. Returns UTC datetime or None."""
    if not text:
        return None

    text = text.strip()

    # ISO datetime with timezone: 2026-04-01T00:00:00-05:00
    if re.match(r"\d{4}-\d{2}-\d{2}T", text):
        try:
            dt = datetime.fromisoformat(text)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

    # ISO date: 2026-04-01
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        try:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # MM.DD.YYYY (Senate Judiciary)
    if re.match(r"^\d{2}\.\d{2}\.\d{4}$", text):
        try:
            return datetime.strptime(text, "%m.%d.%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # M.D.YY or M.DD.YY (trailing date in judiciary letter titles like "3.13.25")
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})$", text)
    if m:
        try:
            value = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
            return datetime.strptime(value, "%m/%d/%y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # MM/DD/YY
    if re.match(r"^\d{1,2}/\d{1,2}/\d{2}$", text):
        try:
            return datetime.strptime(text, "%m/%d/%y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # MM/DD/YYYY
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", text):
        try:
            return datetime.strptime(text, "%m/%d/%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # "March 30, 2026" or "April 1, 2026"
    try:
        return datetime.strptime(text, "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # "Mar 30, 2026"
    try:
        return datetime.strptime(text, "%b %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    # "March 30 2026" (no comma)
    try:
        return datetime.strptime(text, "%B %d %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    return None


def compute_content_hash(text: str) -> str:
    """SHA-256 of normalized text content."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()


def is_pdf_url(url: str) -> bool:
    """Check if a URL points to a PDF file."""
    parsed = urlparse(url)
    return parsed.path.lower().endswith(".pdf")


def clean_text(text: str) -> str:
    """Normalize whitespace and strip HTML artifacts from text."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()
