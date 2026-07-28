# Congressional investigations tracker

A small system that watches congressional committee websites for new investigations, letters, and press releases. It collects everything onto one filterable page and sends a weekly email digest. It runs itself: a scheduled job checks the sources every morning, and nobody has to remember to look.

I built this with [Claude Code](https://claude.com/claude-code), and I published this copy so other people can read the code, run it, and reuse the pattern for their own monitoring projects.

## How it works

The system has two loops.

**The daily capture loop** (GitHub Actions, every morning):

1. Fetch 16 committee pages listed in `config/sources.yml` (House and Senate, majority and minority).
2. Parse each page with a parser matched to its HTML structure (`src/app/parsers/`).
3. Normalize and deduplicate the items, then diff them against the last run (`data/state.json`).
4. Render a static page (`site/index.html`) and a JSON feed (`site/feed.json`).
5. Commit the results. Vercel serves the updated page.

**The weekly email loop** (Vercel cron, Monday mornings):

1. A cron job calls `api/email.js` with a secret key.
2. The function reads `site/feed.json`, keeps the items first seen in the past week, and builds the email.
3. [Resend](https://resend.com) delivers it to the recipient list.

There is also a feedback channel: readers can right-click anywhere on the page to flag an item or a mistake. Flags go to a Redis queue (`api/feedback.js`) and get exported for review.

## A tour of the repo

| Path | What it is |
|---|---|
| `src/app/` | The Python pipeline: fetch, parse, normalize, diff, render |
| `src/app/parsers/` | One parser module per page structure, registered with a decorator |
| `config/sources.yml` | The source list: URLs, committee names, parser assignments |
| `api/` | Vercel serverless functions: weekly email, feedback, click stats, recipients |
| `site/` | The generated page, feed, and hand-managed helper pages |
| `data/` | Current state, item history, and the feedback queue |
| `tests/` | 91 tests: parser fixtures, pipeline behavior, API contracts |
| `docs/adr/` | Architecture decision records explaining the bigger choices |
| `scripts/` | Setup and smoke-test scripts |
| `.github/workflows/daily.yml` | The daily schedule |
| `.claude/skills/tracker-builder/` | The reusable process I follow to build trackers like this |

## Run it locally

You need Python 3.12 or newer.

```bash
pip install -e .
python -m app.cli run       # fetch everything and rebuild the site
open site/index.html        # view the result
python -m pytest            # run the tests
```

The pipeline writes `site/index.html`, `site/feed.json`, and `data/state.json`. Running it twice shows the diffing: the second run reports only genuinely new items.

## Deploy your own

1. Fork or clone this repo and push it to your GitHub account.
2. Import the repo into Vercel as a static project (no build command; the page is committed HTML).
3. Copy `.env.example` values into `.env.local` and fill them in: a Resend API key, sender and recipient addresses, an Upstash Redis URL and token for feedback, and secrets for the cron and admin routes.
4. Run `bash scripts/setup-env.sh` to push the values to Vercel and GitHub.
5. Enable the GitHub Action. The daily loop starts on the next scheduled run.

The email sends only when the cron secret matches, so nothing goes out by accident while you are setting up.

## How I built it

The honest answer is that I described what I wanted to Claude Code, reviewed what it built, and corrected it until the output matched what the reader needed. The repo shows the habits that made that work:

- **Tests before trust.** Every parser has a saved HTML fixture and an exact expected item count. When a committee redesigns its page, a test fails before a reader sees a gap.
- **Decision records.** `docs/adr/` explains why the email reads from the deployed feed, why the collector is separate from the command-line entry point, and other choices future sessions would otherwise re-litigate.
- **A skill file.** `.claude/skills/tracker-builder/SKILL.md` is the written process I hand to Claude when I start a new tracker: what to ask the person who will use it, what to build first, and what every tracker page needs. It is the most reusable thing in this repo.
- **Health checks.** The pipeline refuses to save state that looks like a regression (dates going backward, item counts collapsing), because the most dangerous failure is the silent one.

If you are starting from zero with AI tools, I made a short tutorial site that covers the basics: [learn-ai-with-sean.vercel.app](https://learn-ai-with-sean.vercel.app).

## License

MIT. Use anything here for your own projects.
