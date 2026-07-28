---
name: tracker-builder
description: Turn a person's monitoring need into a working tracker. Use when someone wants to watch a set of websites, filings, or feeds and receive the new items as a page or a scheduled email. Interview first, build the smallest showable thing second, automate last.
---

# Tracker Builder

This is the process behind the congressional investigations tracker and several trackers like it. It is written as a skill: a reusable instruction file an AI coding agent loads when the task matches. You are welcome to adapt it.

The one-sentence version: interview the future reader before writing code, show the smallest useful artifact, and only then automate the schedule, the email, and the feedback loop.

## First rule

Start from the person's work, not from the available tools. A tracker exists to replace a checking habit someone already has. If you cannot name the habit it replaces, you are not ready to build.

## Workflow

1. **Ground the ask.** Write down what the person asked for and what must be true for the result to count as useful.
2. **Interview for the job.** One to three questions at a time, in plain language. The list below usually covers it in about five turns.
3. **Test source feasibility.** Before building, verify each source can be fetched, parsed, deduplicated, and revisited. Fetch the real pages and read the real HTML. Page structures never match your assumptions.
4. **Choose the smallest showable output.** A static page built from one day's real data beats a plan for a full app. Show it, then ask what is wrong with it.
5. **Build behind gates.** Creating repos, scheduling jobs, sending email, and contacting the stakeholder are separate steps that each get explicit approval.
6. **Calibrate from feedback.** When the reader corrects something, separate the one-time fix from the durable lesson, and write the lesson down where the next project will find it.

## Interview questions

1. What do you check today, and what makes the current process painful?
2. When a new item appears, what question do you need answered?
3. Which sources matter first, and how do new items appear there?
4. What would make the output useful: a list of new items, a summary, a classification, or source-backed analysis?
5. Who reviews the output, and what would they need to verify?
6. What kind of miss or wrong answer would be costly?
7. How often do the sources change, and when should the tracker run?
8. How do you want to receive it: an email you can forward, or a page you open? Resolve this early. It changes what you build. Many people want the email.
9. How often should it arrive: intraday, daily, or weekly? Follow the reader's decision and the source's own update rhythm. Never assume daily.
10. Can you show me a recent example of something you like, and tell me about an automation that failed for you before? Both answers become written requirements.

When part of an answer is already known, restate the known part and ask only for the missing piece. Save the interview answers verbatim in a dated notes file before deriving a plan.

## What every tracker page gets without being asked

Readers want these and almost never request them. Build them by default, and do not announce them as features:

- **Filtering and search** on every table: per-column filters, one search box, active filters shown as removable chips, a count line that reads "N of M shown," and a zero-result state that offers a reset instead of a bare empty table.
- **Spreadsheet-style tables** for dense review: gridlines, uniform row heights, sticky headers, and a detail view that opens as an overlay instead of shearing the grid.
- **Deep links** so every item in an email links to its highlighted row on the page.
- **A feedback channel** on the page itself, so a reader can flag a wrong or missing item where they see it.
- **A sources registry** once more than a handful of sources exist, so the reader can see what is covered and what is not.

The guardrail: defaults are capabilities, not content decisions. What gets included, how items are grouped, and what the columns mean stay owned by the reader.

## The email contract

If the reader's habit is forwarding an email, the email is the product and the page is the archive.

- The email is built from the same data file the page is built from, so the two can never disagree.
- Window by when the system first saw each item, not by publication date alone, so a late-posted item still gets mentioned once.
- Deduplicate within the email: the same release on two pages is one entry.
- Send on a schedule behind a secret, with a per-period idempotency key so a retried job cannot send twice.
- A successful HTTP response is not a delivered email. Verify a real send to a test address before telling anyone the email works.

## Repo shape

Trackers converge on the same layout. Start with it:

- `config/` — the source list, editable without touching code
- `src/` — the pipeline: fetch, parse, normalize, diff, render
- `data/` — current state and item history, committed by the scheduled job
- `site/` — the generated page and feed; never hand-edit generated files
- `api/` — serverless functions for email, feedback, and stats
- `tests/` — saved HTML fixtures with exact expected item counts per parser
- `docs/adr/` — a short numbered record for each significant decision
- `scripts/` — setup and smoke-test scripts
- `scratchpad.md` — a session log the agent reads at the start of every session and appends to at the end, so lessons survive context resets

## Verification

- Drive the artifact yourself before showing it: open the page, use the filters, click the links, send the test email.
- Add health checks to the pipeline: refuse to save state when dates move backward or item counts collapse. The dangerous failure is the silent one.
- "The job ran" and "the data is right" are different claims. Check the data.
