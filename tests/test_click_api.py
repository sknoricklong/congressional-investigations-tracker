import io
import json

from api import click as click_api
from api import stats as stats_api


def make_handler(handler_class, body: bytes = b"", headers: dict | None = None):
    instance = object.__new__(handler_class)
    instance.headers = headers or {}
    instance.rfile = io.BytesIO(body)
    instance.wfile = io.BytesIO()
    instance.responses = []
    instance.response_headers = []
    instance.send_response = lambda code: instance.responses.append(code)
    instance.send_header = lambda key, value: instance.response_headers.append((key, value))
    instance.end_headers = lambda: None
    return instance


def test_click_post_validates_url_and_keeps_event_shape(monkeypatch):
    missing = make_handler(
        click_api.handler,
        b'{"title":"No URL"}',
        {"Content-Length": str(len(b'{"title":"No URL"}'))},
    )
    missing.do_POST()
    assert missing.responses == [400]
    assert json.loads(missing.wfile.getvalue()) == {"error": "missing url"}

    stored = []
    payload = {
        "url": "https://example.com/release",
        "title": "Release",
        "source": "Source",
        "committee": "Committee",
        "timestamp": "2026-07-28T12:00:00Z",
        "ignored": "not stored",
    }
    raw = json.dumps(payload).encode()
    valid = make_handler(
        click_api.handler,
        raw,
        {"Content-Length": str(len(raw))},
    )
    monkeypatch.setattr(click_api, "_kv_command", lambda command: stored.append(command) or {})

    valid.do_POST()

    assert valid.responses == [200]
    assert json.loads(valid.wfile.getvalue()) == {"ok": True}
    assert stored[0][:2] == ["LPUSH", "clicks"]
    assert json.loads(stored[0][2]) == {
        "url": payload["url"],
        "title": payload["title"],
        "source": payload["source"],
        "committee": payload["committee"],
        "timestamp": payload["timestamp"],
    }
    assert ("Access-Control-Allow-Origin", "*") in valid.response_headers


def test_click_options_keeps_cors_contract():
    request = make_handler(click_api.handler)

    request.do_OPTIONS()

    assert request.responses == [200]
    assert ("Access-Control-Allow-Origin", "*") in request.response_headers
    assert ("Access-Control-Allow-Methods", "POST, OPTIONS") in request.response_headers
    assert ("Access-Control-Allow-Headers", "Content-Type") in request.response_headers


def test_click_returns_500_for_invalid_json():
    request = make_handler(
        click_api.handler,
        b"{",
        {"Content-Length": "1"},
    )

    request.do_POST()
    payload = json.loads(request.wfile.getvalue())

    assert request.responses == [500]
    assert set(payload) == {"error"}


def test_stats_returns_valid_clicks_and_skips_bad_rows(monkeypatch):
    rows = [
        json.dumps({"url": "https://example.com/one", "title": "One"}),
        "{bad",
        None,
        json.dumps({"url": "https://example.com/two", "title": "Two"}),
    ]
    monkeypatch.setattr(stats_api, "_kv_command", lambda command: {"result": rows})
    request = make_handler(stats_api.handler)

    request.do_GET()
    payload = json.loads(request.wfile.getvalue())

    assert request.responses == [200]
    assert payload == {
        "clicks": [
            {"url": "https://example.com/one", "title": "One"},
            {"url": "https://example.com/two", "title": "Two"},
        ],
        "total": 2,
    }
    assert ("Access-Control-Allow-Origin", "*") in request.response_headers


def test_stats_returns_500_when_redis_read_fails(monkeypatch):
    def fail(_command):
        raise RuntimeError("mock read failure")

    monkeypatch.setattr(stats_api, "_kv_command", fail)
    request = make_handler(stats_api.handler)

    request.do_GET()

    assert request.responses == [500]
    assert json.loads(request.wfile.getvalue()) == {
        "error": "mock read failure"
    }
