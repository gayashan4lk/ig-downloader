# Development Guide

Everything needed to change this project safely. See [ARCHITECTURE.md](ARCHITECTURE.md) for
how the code is laid out and why.

## Setup

[uv](https://docs.astral.sh/uv/) is the only prerequisite — it provides the Python interpreter
too, so the system Python (3.9.6 on this machine) is never used.

```sh
uv sync          # creates .venv, installs instaloader + ruff + ty from uv.lock
```

Check the environment:

```sh
uv run python -V        # -> Python 3.12.13
uv run main.py --help
```

No environment variables, no `.env`, no config file. The only state outside the repo is the
cached login session at `~/.config/instaloader/session-<username>`.

## Daily commands

| Task | Command |
|---|---|
| Run | `uv run main.py --profile natgeo --limit 20` |
| Install / refresh deps | `uv sync` |
| Lint | `uv run ruff check .` |
| Lint + autofix | `uv run ruff check --fix .` |
| Format | `uv run ruff format .` |
| Format check (no writes) | `uv run ruff format --check .` |
| Type check | `uv run ty check main.py` |
| Add a runtime dependency | `uv add <pkg>` |
| Add a dev dependency | `uv add --dev <pkg>` |
| Upgrade a dependency | `uv lock --upgrade-package instaloader` |

Always go through `uv run`. Invoking `python main.py` directly uses whatever interpreter is on
`PATH` and will hit the "instaloader is not installed. Run: uv sync" guard.

## Git workflow

1. Branch off `main` (`docs/…`, `fix/…`, `feat/…`). `main` is the default branch.
2. Make the change, then run the full gate:
   ```sh
   uv run ruff format --check . && uv run ruff check . && uv run ty check main.py
   ```
   All three must pass.
3. Work through the [manual verification checklist](#manual-verification-checklist) — there are
   no automated tests to catch you.
4. Update docs that the change invalidates: the README options table for a new flag,
   [ARCHITECTURE.md](ARCHITECTURE.md) for structural changes (and drop any Known-limitations
   row you fixed), the requirement status in [PRD.md](PRD.md#6-functional-requirements), and
   the [ROADMAP.md](ROADMAP.md) item. Add an ADR for any choice someone might later question.
5. Don't commit or push unless asked.

## Testing strategy

**There is no test suite.** This is a deliberate, revisitable choice
([ADR-5](ARCHITECTURE.md#adr-5-ruff-and-ty-no-pytest)) — correctness currently rests on the
manual checklist below.

If you add tests, `uv add --dev pytest` and start with the pure functions, which need no
network and no stubbing:

| Layer | What to cover | Target |
|---|---|---|
| Pure functions | `shortcode_from_url` across `/p/`, `/reel/`, `/reels/`, `/tv/` and bare-shortcode inputs; `parse_date` accepting `YYYY-MM-DD` and rejecting junk | [main.py:74](../main.py#L74), [main.py:81](../main.py#L81) |
| Filter loop | `download_posts` honouring `--limit`, `--since`, `--until` | [main.py:91](../main.py#L91) |
| Known bugs (write these first, as failing tests) | a post at 10:00 UTC on the `--until` day is kept; an old post first in the feed doesn't stop `--since`; `--limit 0` is rejected; `shortcode_from_url("…/p/ABC?img_index=2") == "ABC"` | [ROADMAP P1/P2](ROADMAP.md#next-up) |
| CLI wiring | Exit code 2 for bad flag combinations | [main.py:113](../main.py#L113) |

Rules of thumb:
- **Unit tests must never hit the network.** `download_posts` takes the loader and the post
  iterable as parameters precisely so both can be stubbed: pass a fake loader exposing
  `download_post(post, target)` and a list of objects with a `date_utc` attribute.
- Don't stub `Instaloader` itself. Test `build_loader()` by asserting on the constructed
  object's attributes, not by mocking the constructor.
- Assert on exit codes, not on printed text — messages are user-facing copy and will change.

## Manual verification checklist

Offline checks — these need no network and should always pass:

```sh
uv run main.py --help                                  # help renders; deps import cleanly
uv run main.py                                         # exit 2: "one of the arguments ... is required"
uv run main.py --saved                                 # exit 2: "--saved requires --login"
uv run main.py --profile natgeo --since 2025-13-99     # exit 2: "Use YYYY-MM-DD, got '2025-13-99'"
```

Check the exit code with `echo $?` — argparse failures must be 2, not 1.

Real download — **the maintainer verifies this by hand**; don't run repeated live download
attempts. Write output to a temp directory, never into the repo:

```sh
uv run main.py --profile natgeo --limit 2 --out /tmp/ig-smoke
find /tmp/ig-smoke -type f
```

Expected: `.jpg` files only under `/tmp/ig-smoke/natgeo/`, named
`YYYY-MM-DD_HH-MM-SS_<shortcode>.jpg` (carousels add `_1`, `_2`, …, so two posts can mean more
than two files, and a video-only post means fewer). No videos, no `.txt` or `.json` sidecars,
exit 0.

Known-bad inputs, so nobody wastes time on them:
- **Anonymous `--profile` is unreliable.** On 2026-09-30 repeated attempts returned
  `401 "Please wait a few minutes before you try again."` for the public `natgeo` profile. A
  rate-limit exit (code 1, "Connection/rate-limit problem: …", no traceback) confirms the error
  path but does *not* confirm downloading works. Use `--login` for a real check.
- `--saved --since <date>` may under-report, `--profile --since` can return 0 when an old post
  is pinned, and `--until <date>` excludes that date. These are known bugs, not regressions;
  see [Known limitations](ARCHITECTURE.md#known-limitations).
- The filter logic in `download_posts()` can be checked offline, without a real loader. Pass
  a stub with `download_post(post, target)` and a list of objects carrying `date_utc`. That is
  how the bugs above were confirmed.

## Adding a new flag

Worked example, following how `--include-videos` is wired:

1. **Declare it** in `main()` beside the related flags
   ([main.py:116-125](../main.py#L116-L125)). Group it in the mutually exclusive `src` group
   only if it is a new *source*.
2. **Validate combinations** right after `parse_args()` ([main.py:128](../main.py#L128)) using
   `ap.error("...")` as a statement — it exits 2 and never returns.
3. **Thread the value** to the function that consumes it. If it changes what instaloader
   writes, it belongs in `build_loader()` and nowhere else. If it filters posts, extend
   `download_posts()`'s signature — keep it fully annotated, it is type-checked.
4. **Run the gate**: `uv run ruff format . && uv run ruff check . && uv run ty check main.py`.
5. **Document it**: add a row to the README options table, and update the module docstring's
   examples if it deserves one.
6. **Record the reasoning** as an ADR in [ARCHITECTURE.md](ARCHITECTURE.md#decisions) if the
   choice was non-obvious.

## Code conventions

- **Python 3.12.** Modern syntax is fine (`int | None` unions, no `__future__` imports).
- **Annotate new functions fully.** `ty` runs over `main.py`; unannotated parameters silently
  skip checking.
- **Lint selection** is `E`, `F`, `I`, `UP`, `B`, `SIM` at `line-length = 100`
  ([ADR-6](ARCHITECTURE.md#adr-6-line-length--100)). Let `ruff format` settle formatting
  arguments; note that a trailing comma in a call forces one argument per line.
- **Errors are messages, not tracebacks.** Every expected failure is caught in `main()` and
  reported as one actionable line on `stderr` with a non-zero return. Never let an
  `instaloader` exception escape.
- **Exit codes** follow the table in [ARCHITECTURE.md](ARCHITECTURE.md#outputs-and-exit-codes):
  0 success, 1 runtime/network failure, 2 bad flags, 130 Ctrl-C.
- **User-facing copy** is lowercase-sentence style and says what to do next ("Re-run with
  `--login <username>`"), not just what broke.
- Comments explain *why*. Several existing ones guard deliberate oddities — see the
  [quirks table](ARCHITECTURE.md#quirks-and-workarounds) before removing any.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `instaloader is not installed. Run: uv sync` | Ran `python main.py` with a non-project interpreter | Use `uv run main.py` |
| `401 ... "Please wait a few minutes before you try again."` | Instagram rate-limiting anonymous API access | Wait; re-run with `--login`; lower `--limit` |
| `Connection/rate-limit problem: …` then exit 1 | Three attempts exhausted ([main.py:45](../main.py#L45)) | Wait before retrying — this is the designed graceful exit, not a crash |
| `Instagram wants a login for this.` | Content needs auth | Re-run with `--login <username>` |
| `<user> is private and you don't follow them.` | Private profile | Follow the account, or use an account that does, via `--login` |
| Password prompt on every run | Session file missing or unreadable | Check `~/.config/instaloader/session-<username>`; it is written after a successful fresh login ([main.py:69-71](../main.py#L69-L71)) |
| `--saved` returns fewer posts than expected | `--since` short-circuits on save-ordered feeds | Drop `--since`, use `--limit`; see [Known limitations](ARCHITECTURE.md#known-limitations) |
| `--profile X --since D` downloads 0 posts | An old pinned post at the top of the feed ends the loop | Drop `--since`; see [Known limitations](ARCHITECTURE.md#known-limitations) |
| Posts from the `--until` day are missing | `--until` is compared as 00:00 UTC of that day | Pass the next day |
| Traceback ending in `BadCredentialsException` / `LoginException` | Wrong password or 2FA code, or a blocked login. The login path is outside `main()`'s `try`. | Re-run and retype; tracked in [ROADMAP P1](ROADMAP.md#p1-correct-filters-and-no-tracebacks) |
| Traceback ending in `BadResponseException: Fetching Post metadata failed.` | Mistyped or deleted `--post` shortcode | Check the URL. A URL with `?` right after the shortcode isn't parsed; trim the query string |
| Logged-in run fails with a login/connection error that used to work | Cached session expired; it is never re-validated | Delete `~/.config/instaloader/session-<username>` and re-run to get the password prompt |
| Videos appearing in output | `--include-videos` was passed, or `build_loader()` defaults were edited | Check [main.py:33-47](../main.py#L33-L47) |
| `ty` reports unresolved `instaloader` | `.venv` missing or stale | `uv sync`. Do **not** silence it with a `[tool.ty.rules]` ignore — it resolves cleanly in a synced env |
