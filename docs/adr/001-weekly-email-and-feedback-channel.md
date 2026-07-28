# ADR 001: Weekly email pipeline and right-click feedback channel

Date: 2026-07-24
Status: Accepted

## Context

The reader asked for the tracker pushed as an email, weekly. The site had no
send path, no feedback channel, and no recipients management. Several earlier
trackers built on the same pattern share worked solutions for all three.

## Decision

**Three clocks.** Capture stays daily (GitHub Actions, 09:00 UTC). Draft and
send are one step, weekly: Vercel cron fires `/api/email` Mondays 13:00 UTC
(9:00 AM EDT; 8:00 AM EST after the November DST change — cron is UTC and
ignores DST).

**Send path (`api/email.js`).** Dependency-free Node on Vercel, sending via
the Resend HTTP API from a domain Sean owns. The function
`require`s `../site/feed.json` — the same file the page serves, bundled at
deploy time — so page and email can never diverge and no live committee-page
fetch happens at send time. Selection windows on `first_seen_at` (first
capture time, written once, never rewritten), not publication date: committee
pages stamp date-only publication dates and items can enter the tracker days
late. Window is 170h (168h + 2h jitter/deploy-race bias; a rare duplicate
across two issues is acceptable, a silently missed item is not).

Send-path verification hardening, all from the CNMV failures: gate trusts
only `Authorization: Bearer $CRON_SECRET`; `?dryRun=1` returns gate decision
and item selection unauthenticated; `?includeHtml=1` returns the exact email
body (one builder — the preview page injects it); `?testEmail=1&key=$CONGRESS_TEST_SECRET`
sends only to the test inbox with a `[Test]` prefix and no idempotency key;
`?sendEmail=1` is the manual production trigger; one Resend idempotency key
per issue week; a Resend 409 is a suppressed duplicate, not an error; missing
config throws 502, never a silent 200; every run logs one structured
`cron-run` line; responses are `no-store`.

**Recipients (`api/recipients.js`, `site/recipients.html`).** Resend audience
"Congressional investigations tracker", looked up by name, seeded from
`CONGRESS_EMAIL_TO` on first use, env var kept as send-time fallback.
POST-only, timing-safe password compare with a flat delay, last-recipient
guard, operator addresses hidden from the stakeholder view.

**Feedback (`api/feedback.js`, `-export`, `-status`).** Right-click anywhere
on the page → context menu → note popover → POST with item data, target
region/column/text, and active filters. Stored in the shared tracker Upstash
Redis under the per-tracker key `congressional_investigations_feedback`.
Mailto fallback to Sean's firm address when the API is down or unconfigured.
The daily workflow snapshots `status=new` records into
`data/feedback-queue.json` when `FEEDBACK_ADMIN_SECRET` is set, and skips
quietly when it is not.

**Pre-commit hook narrowed.** `site/` static pages (stats.html, email.html,
recipients.html) are hand-managed; the hook now protects only the
pipeline-written paths: `data/`, `logs/`, `site/index.html`,
`site/feed.json`.

## Env vars (all set by Sean; every path degrades until they exist)

Vercel: `RESEND_API_KEY` (full access, for audience calls), `CRON_SECRET`,
`CONGRESS_EMAIL_FROM`, `CONGRESS_EMAIL_TO`, `CONGRESS_EMAIL_TEST_TO`
(optional), `CONGRESS_TEST_SECRET`, `CONGRESS_LIST_PASSWORD`,
`UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`,
`FEEDBACK_ADMIN_SECRET`. GitHub Actions: `FEEDBACK_ADMIN_SECRET`.

## Alternatives considered

- Emailing from GitHub Actions on the capture schedule: rejected — scheduled
  Actions fire 1-3h late or skip; Vercel cron is the family's proven trigger.
- Fetching the live site at send time: rejected — the bundled-data pattern
  (german) removes the divergence and the fragile fetch.
- Daily email: the partner asked for weekly.
