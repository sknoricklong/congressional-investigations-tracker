# ADR 002: Separate collection work from command handling

Date: 2026-07-28
Status: Accepted

## Context

`src/app/cli.py` handles two different jobs. It defines the four command line
commands, and it also fetches sources, fills missing dates and titles, checks
health, saves results, and renders the site.

The collection code is the largest part of the file. Tests must import the
command module to check collection behavior. A change to a command can also
make the collection code harder to review.

## Decision

Move source collection and run control to `src/app/pipeline.py`.

`pipeline.py` will own:

- parser registration
- one source collection run
- missing date and truncated title lookups
- health checks
- state, history, run log, and render control

`cli.py` will own:

- Typer setup
- the `run`, `test-source`, `render`, and `list-sources` commands
- command output and exit behavior

`cli.py` will call `process_source()` and `run_pipeline()` from
`pipeline.py`. The move will keep the current source order, requests, retries,
saved data, render calls, log messages, and exit rules.

No new base class, service object, or dependency will be added.

## Consequences

- Collection behavior can be tested without loading command handling.
- The four commands remain in one short file.
- The collector has one clear home.
- A collector change may still touch both files when a command needs a new
  option.
- Internal imports of the old private functions in `cli.py` must move to
  `pipeline.py`. No public command or route changes.
