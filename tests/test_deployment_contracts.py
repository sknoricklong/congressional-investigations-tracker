import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def test_production_schedules_and_retry_rule_are_unchanged():
    vercel = json.loads((PROJECT_ROOT / "vercel.json").read_text())
    workflow = (PROJECT_ROOT / ".github/workflows/daily.yml").read_text()

    assert vercel["crons"] == [
        {"path": "/api/email", "schedule": "0 13 * * 1"}
    ]
    assert "- cron: '0 9 * * *'" in workflow
    assert "sleep 900" in workflow
    assert workflow.count("python -m app.cli run") == 2
    assert "node scripts/smoke-email.js" in workflow


def test_weekly_email_and_feedback_environment_names_are_unchanged():
    setup_script = (PROJECT_ROOT / "scripts/setup-env.sh").read_text()
    variables_block = re.search(r"VARS=\((.*?)\)\nfor v", setup_script, re.DOTALL)
    assert variables_block is not None

    variables = re.findall(r"[A-Z][A-Z0-9_]+", variables_block.group(1))
    assert variables == [
        "RESEND_API_KEY",
        "CRON_SECRET",
        "CONGRESS_EMAIL_FROM",
        "CONGRESS_EMAIL_TO",
        "CONGRESS_EMAIL_TEST_TO",
        "CONGRESS_TEST_SECRET",
        "CONGRESS_LIST_PASSWORD",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "FEEDBACK_ADMIN_SECRET",
    ]


def test_click_routes_keep_legacy_redis_environment_names_and_key():
    click_source = (PROJECT_ROOT / "api/click.py").read_text()
    stats_source = (PROJECT_ROOT / "api/stats.py").read_text()

    for source in (click_source, stats_source):
        assert 'os.environ.get("KV_REST_API_URL", "")' in source
        assert 'os.environ.get("KV_REST_API_TOKEN", "")' in source
        assert '"clicks"' in source
