from __future__ import annotations

import asyncio
import logging
import time

import httpx

from app.models import SourceConfig

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 "
    "CongressMonitor/0.1"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Rate limiting: track last request time per domain
_domain_last_request: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 1.0

MAX_RETRIES = 3
RETRY_BACKOFF = [1.0, 2.0, 4.0]
REQUEST_TIMEOUT = 30.0


async def _rate_limit(domain: str) -> None:
    """Wait if needed to respect per-domain rate limit."""
    now = time.monotonic()
    last = _domain_last_request.get(domain, 0.0)
    wait = _RATE_LIMIT_SECONDS - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)
    _domain_last_request[domain] = time.monotonic()


async def fetch_page(url: str, client: httpx.AsyncClient) -> str:
    """Fetch a single page with retry and rate limiting. Returns HTML string."""
    from urllib.parse import urlparse

    domain = urlparse(url).netloc
    await _rate_limit(domain)

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.get(url, follow_redirects=True, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.warning(
                    f"Fetch attempt {attempt + 1} failed for {url}: {e}. "
                    f"Retrying in {wait}s."
                )
                await asyncio.sleep(wait)
            else:
                logger.error(f"All {MAX_RETRIES} fetch attempts failed for {url}: {e}")

    raise last_error  # type: ignore[misc]


async def fetch_source(source: SourceConfig, client: httpx.AsyncClient) -> list[str]:
    """Fetch the list page(s) for a source. Returns list of HTML strings (one per page).

    For the MVP, fetches only page 1. Pagination support can be added later.
    """
    try:
        html = await fetch_page(source.url, client)
        return [html]
    except Exception as e:
        logger.error(f"Failed to fetch source {source.id}: {e}")
        raise


def create_client() -> httpx.AsyncClient:
    """Create a configured httpx client."""
    return httpx.AsyncClient(headers=DEFAULT_HEADERS)
