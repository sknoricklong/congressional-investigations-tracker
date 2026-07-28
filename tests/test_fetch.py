from types import SimpleNamespace

import httpx
import pytest

from app import fetch
from app.models import SourceConfig


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class SequenceClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_source() -> SourceConfig:
    return SourceConfig(
        id="source",
        name="Source",
        committee="Committee",
        chamber="House",
        party_lane="majority",
        url="https://example.com/releases",
        collection="press",
        kind="press_release",
        tier="tier1",
        parser="parser",
    )


@pytest.mark.asyncio
async def test_rate_limit_waits_for_repeated_domain(monkeypatch):
    fetch._domain_last_request.clear()
    times = iter([10.0, 10.0, 10.25, 11.0])
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(fetch, "time", SimpleNamespace(monotonic=lambda: next(times)))
    monkeypatch.setattr(fetch.asyncio, "sleep", fake_sleep)

    await fetch._rate_limit("example.com")
    await fetch._rate_limit("example.com")

    assert waits == [0.75]
    assert fetch._domain_last_request["example.com"] == 11.0


@pytest.mark.asyncio
async def test_fetch_page_retries_twice_with_current_timeout_and_backoff(monkeypatch):
    request = httpx.Request("GET", "https://example.com/releases")
    client = SequenceClient(
        [
            httpx.ConnectError("first", request=request),
            httpx.ConnectError("second", request=request),
            FakeResponse("<html>ok</html>"),
        ]
    )
    waits = []

    async def no_rate_limit(_domain):
        return None

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(fetch, "_rate_limit", no_rate_limit)
    monkeypatch.setattr(fetch.asyncio, "sleep", fake_sleep)

    html = await fetch.fetch_page("https://example.com/releases", client)

    assert html == "<html>ok</html>"
    assert len(client.calls) == 3
    assert waits == [1.0, 2.0]
    assert all(call[1]["follow_redirects"] is True for call in client.calls)
    assert all(call[1]["timeout"] == 30.0 for call in client.calls)


@pytest.mark.asyncio
async def test_fetch_page_raises_after_three_attempts(monkeypatch):
    request = httpx.Request("GET", "https://example.com/releases")
    errors = [httpx.ConnectError(str(index), request=request) for index in range(3)]
    client = SequenceClient(errors)

    async def no_wait(_value):
        return None

    monkeypatch.setattr(fetch, "_rate_limit", no_wait)
    monkeypatch.setattr(fetch.asyncio, "sleep", no_wait)

    with pytest.raises(httpx.ConnectError, match="2"):
        await fetch.fetch_page("https://example.com/releases", client)
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_fetch_source_returns_one_list_page(monkeypatch):
    async def fake_fetch_page(url, client):
        assert url == "https://example.com/releases"
        assert client == "client"
        return "<html>source</html>"

    monkeypatch.setattr(fetch, "fetch_page", fake_fetch_page)

    assert await fetch.fetch_source(make_source(), "client") == ["<html>source</html>"]


@pytest.mark.asyncio
async def test_create_client_keeps_headers_and_timeout_at_request_level():
    client = fetch.create_client()
    try:
        assert client.headers["User-Agent"] == fetch.USER_AGENT
        assert "text/html" in client.headers["Accept"]
        assert client.timeout.connect == 5.0
    finally:
        await client.aclose()

    assert fetch.MAX_RETRIES == 3
    assert fetch.RETRY_BACKOFF == [1.0, 2.0, 4.0]
    assert fetch.REQUEST_TIMEOUT == 30.0
    assert fetch._RATE_LIMIT_SECONDS == 1.0
