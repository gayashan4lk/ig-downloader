# CLAUDE.md

Guidance for AI coding assistants (and people) working on this repo.

## Project

`ig-downloader` is a single-file Python CLI that downloads images from Instagram — a public
profile's posts, one post by URL, or your own saved collection. It wraps
[instaloader](https://instaloader.github.io/) with images-only defaults and is managed with
[uv](https://docs.astral.sh/uv/).

Docs: [Architecture + decisions](docs/ARCHITECTURE.md) · [Development guide](docs/DEVELOPMENT.md)

## Commands

```bash
uv sync                                      # set up / refresh the environment
uv run main.py --profile natgeo --limit 20   # run
uv run ruff format . && uv run ruff check .  # format + lint
uv run ty check main.py                      # type check
```

Always invoke through `uv run`. There is no test suite. The system Python is 3.9.6 and must
never be used; the project pins 3.12.

## Layout

- `main.py`: the entire tool — arg parsing, login, download loop, error-to-exit-code mapping.
- `pyproject.toml`: deps + ruff config. `uv.lock` is committed; keep it in sync.
- `docs/`: architecture (with the decision log folded in) and the development guide.

Flat by design — no `src/`, no package, no console-script entry point
([ADR-2](docs/ARCHITECTURE.md#adr-2-flat-layout-not-a-package)).

## Rules

- **Instaloader behaviour is centralised in `build_loader()`** ([main.py:33](main.py#L33)).
  Anything changing what lands on disk goes there and nowhere else.
- **Reuse `download_posts()`** ([main.py:91](main.py#L91)) for any new post source; don't write
  a second download loop.
- **Annotate every new function fully** — `ty` skips unannotated parameters.
- **Never let an exception escape `main()`.** Catch it, print one actionable line to `stderr`,
  return non-zero. Exit codes: 0 success, 1 runtime/network failure, 2 bad flags, 130 Ctrl-C.
- **Don't remove these deliberate oddities** (full reasons in the
  [quirks table](docs/ARCHITECTURE.md#quirks-and-workarounds)): the function-local
  `import getpass`; `raise ... from None` in `parse_date`; `ap.error(...)` called as a
  statement rather than returned; the `try: import instaloader` guard.
- **Don't add a `[tool.ty.rules]` ignore for `instaloader`** — it resolves cleanly in a synced
  environment; an unresolved-import error means `uv sync` is needed.
- Lint is `E,F,I,UP,B,SIM` at `line-length = 100`. Don't change the line length to match ruff's
  default without reading [ADR-6](docs/ARCHITECTURE.md#adr-6-line-length--100).
- If tests are ever added, **unit tests must not hit the network**. `download_posts` takes its
  loader and post iterable as parameters so both can be stubbed.
- Git: branch off `main` (`fix/…`, `feat/…`, `docs/…`); don't commit or push unless asked.
- After a change, update the README options table (new flags) and
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (structure, or a new ADR for non-obvious calls).

## Verifying real behaviour

Run the offline checks — help text plus the three argparse failure paths — as listed in the
[verification checklist](docs/DEVELOPMENT.md#manual-verification-checklist), confirming exit
code 2 on each failure.

**Do not run live download attempts to verify a change.** The maintainer tests real downloads
by hand. Anonymous `--profile` access is rate-limited to the point of uselessness (observed
2026-09-30: repeated `401 "Please wait a few minutes before you try again."` on the public
`natgeo` profile), and retrying risks throttling the account they need. Report a real download
as unverified and hand over the command instead.

If a download check is explicitly requested, write output to a temp directory
(`--out /tmp/ig-smoke`), never into the repo.

## Scope

A personal tool for downloading images the user can already access — public profiles, and
private or saved content via their own authenticated session. Keep it that way: no scraping of
content the logged-in user cannot see, no bulk harvesting across many accounts, and no working
around Instagram's rate limits (the 3-attempt cap and 30s timeout in `build_loader()` are a
deliberate ceiling, not an obstacle to route around).
