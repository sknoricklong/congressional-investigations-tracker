"""Tests for URL canonicalization, date parsing, and hashing."""
from datetime import datetime, timezone

from app.utils import canonicalize_url, compute_content_hash, is_pdf_url, parse_date


class TestCanonicalizeUrl:
    def test_strips_tracking_params(self):
        url = "https://example.com/page?utm_source=twitter&id=123"
        assert canonicalize_url(url) == "https://example.com/page?id=123"

    def test_resolves_relative_url(self):
        result = canonicalize_url("/press/release-1", "https://oversight.house.gov/press/")
        assert result == "https://oversight.house.gov/press/release-1"

    def test_strips_fragment(self):
        assert canonicalize_url("https://example.com/page#section") == "https://example.com/page"

    def test_strips_trailing_slash(self):
        assert canonicalize_url("https://example.com/page/") == "https://example.com/page"

    def test_preserves_root_slash(self):
        assert canonicalize_url("https://example.com/") == "https://example.com/"

    def test_lowercases_scheme_and_host(self):
        assert canonicalize_url("HTTPS://Example.Com/Path") == "https://example.com/Path"


class TestParseDate:
    def test_iso_datetime_with_tz(self):
        result = parse_date("2026-04-01T00:00:00-05:00")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4

    def test_iso_date(self):
        result = parse_date("2026-04-01")
        assert result == datetime(2026, 4, 1, tzinfo=timezone.utc)

    def test_dot_format(self):
        result = parse_date("03.30.2026")
        assert result is not None
        assert result.month == 3
        assert result.day == 30

    def test_slash_short_year(self):
        result = parse_date("04/01/26")
        assert result is not None
        assert result.month == 4
        assert result.day == 1

    def test_slash_full_year(self):
        result = parse_date("03/31/2026")
        assert result is not None
        assert result.month == 3
        assert result.day == 31

    def test_full_month_name(self):
        result = parse_date("March 30, 2026")
        assert result is not None
        assert result.month == 3
        assert result.day == 30

    def test_abbreviated_month(self):
        result = parse_date("Mar 30, 2026")
        assert result is not None
        assert result.month == 3

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_garbage_input(self):
        assert parse_date("not a date") is None


class TestContentHash:
    def test_stable_hash(self):
        h1 = compute_content_hash("Hello World")
        h2 = compute_content_hash("Hello World")
        assert h1 == h2

    def test_whitespace_normalization(self):
        h1 = compute_content_hash("Hello   World")
        h2 = compute_content_hash("Hello World")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_content_hash("Hello World")
        h2 = compute_content_hash("hello world")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = compute_content_hash("Hello")
        h2 = compute_content_hash("Goodbye")
        assert h1 != h2


class TestIsPdfUrl:
    def test_pdf_url(self):
        assert is_pdf_url("https://example.com/document.pdf") is True

    def test_non_pdf_url(self):
        assert is_pdf_url("https://example.com/page") is False

    def test_case_insensitive(self):
        assert is_pdf_url("https://example.com/doc.PDF") is True
