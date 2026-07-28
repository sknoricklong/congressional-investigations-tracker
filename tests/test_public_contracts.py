from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def test_public_pages_keep_current_api_routes_and_methods():
    email_page = (PROJECT_ROOT / "site/email.html").read_text()
    recipients_page = (PROJECT_ROOT / "site/recipients.html").read_text()
    stats_page = (PROJECT_ROOT / "site/stats.html").read_text()
    template = (PROJECT_ROOT / "src/app/templates/index.html.j2").read_text()

    assert "fetch('/api/email?dryRun=1&includeHtml=1'" in email_page
    assert 'fetch("/api/recipients", {' in recipients_page
    assert 'method: "POST"' in recipients_page
    assert "fetch('/api/stats')" in stats_page
    assert "navigator.sendBeacon('/api/click'" in template
    assert "fetch('/api/click', { method: 'POST'" in template
    assert "fetch('/api/feedback', {" in template
    assert "method: 'POST'" in template


def test_feedback_filter_context_does_not_read_removed_checkbox():
    template = (PROJECT_ROOT / "src/app/templates/index.html.j2").read_text()

    assert "newOnlyCheck" not in template
    assert "recent_only: ''" in template
