# Architecture

How `ig-downloader` is put together, why it is shaped this way, and what will surprise you.
One script, one runtime dependency — the [Decisions](#decisions) section is folded in at the
bottom rather than kept in a separate file. See [DEVELOPMENT.md](DEVELOPMENT.md) for how to
set up and change it, [PRD.md](PRD.md) for what it is meant to do, and
[ROADMAP.md](ROADMAP.md) for what to fix next.

## Overview

```
          CLI flags (argparse)
                  |
                  v
      +-----------------------+
      |  main()   main.py:113 |  arg parsing, source dispatch, error -> exit code
      +-----------------------+
         |          |        |
         |          |        +--> login()          main.py:50   (optional)
         |          |                  |                 reads/writes session cache
         |          |                  v
         |          |          ~/.config/instaloader/session-<user>
         |          |
         |          +--> build_loader()  main.py:33   (Instaloader + our defaults)
         |                     |
         v                     v
   download_posts()     instaloader  ---- HTTPS ---->  Instagram web API
     main.py:91                |
        (filter + loop)        v
                        <out>/<target>/<date>_<shortcode>.jpg
```

There is no package, no `src/` directory, and no build backend: `main.py` sits at the repo
root and is run with `uv run main.py`. Everything the tool does lives in that one file.

## Components

All in [main.py](../main.py) — the table is by function, since that is the unit of
responsibility here.

| Function | Responsibility | Side effects | Tests |
|---|---|---|---|
| `main()` ([main.py:113](../main.py#L113)) | Define flags, validate flag combinations, dispatch on source, map exceptions to exit codes | Creates the output dir; prints | none |
| `build_loader()` ([main.py:33](../main.py#L33)) | Construct `Instaloader` with this project's opinionated defaults | none (pure construction) | none |
| `login()` ([main.py:50](../main.py#L50)) | Authenticate, preferring a cached session file over a password prompt | Network; reads/writes session file; prompts on stdin | none |
| `download_posts()` ([main.py:91](../main.py#L91)) | Iterate a post feed applying `--since`/`--until`/`--limit`, download each | Network; writes files via the loader | none |
| `parse_date()` ([main.py:74](../main.py#L74)) | `argparse` type for `YYYY-MM-DD` | none (pure) | none |
| `shortcode_from_url()` ([main.py:81](../main.py#L81)) | Extract a post shortcode from a `/p/`, `/reel/`, `/reels/`, or `/tv/` URL, or pass through a bare shortcode | none (pure) | none |

`parse_date` and `shortcode_from_url` are the only pure, easily testable functions. There is
currently no test suite at all — see [DEVELOPMENT.md](DEVELOPMENT.md#testing-strategy).

## Data flow

1. **Parse.** `argparse` builds the flags. A mutually exclusive, required group enforces
   exactly one of `--profile` / `--post` / `--saved`. `--since` and `--until` run through
   `parse_date`, so a malformed date fails during parsing, before any network call.
2. **Cross-flag validation.** `--saved` without `--login` is rejected via `ap.error()`
   ([main.py:129](../main.py#L129)), which prints usage and exits 2.
3. **Prepare output.** `--out` is expanded and resolved to an absolute path, and the directory
   is created (`parents=True, exist_ok=True`) *before* any network work.
4. **Build the loader.** `build_loader()` bakes in the defaults below. `images_only` is the
   inverse of `--include-videos`.
5. **Authenticate** (only if `--login` was passed). `login()` tries the cached session file
   first and falls back to a `getpass` prompt, handling a 2FA challenge if Instagram asks.
   On a fresh login the session is written back to disk for next time.
6. **Fetch and download**, per source:
   - `--post`: `shortcode_from_url()` → `Post.from_shortcode()` → one `download_post()`.
   - `--profile`: `Profile.from_username()`, refuse early if the profile is private and not
     followed, then `download_posts()` over `profile.get_posts()`.
   - `--saved`: `Profile.from_username(args.login)` then `download_posts()` over
     `profile.get_saved_posts()`.
7. **Map errors to exit codes.** One `try` block around all of step 6 catches four specific
   exception types (plus `KeyboardInterrupt`) and turns each into a one-line message on stderr
   plus a numeric exit code. The intent is that nothing surfaces as a traceback, but steps 3
   and 5 run *outside* that `try`, and several instaloader exception types aren't caught.
   See [Known limitations](#known-limitations).

## Key configuration

There is no config file and no environment variables. Behaviour comes from CLI flags plus the
`Instaloader` defaults set once in `build_loader()` ([main.py:33-47](../main.py#L33-L47)):

| Setting | Value | Why |
|---|---|---|
| `dirname_pattern` | `<out>/{target}` | One subdirectory per profile (or `saved`) |
| `filename_pattern` | `{date_utc:%Y-%m-%d_%H-%M-%S}_{shortcode}` | Chronologically sortable, collision-free names |
| `download_videos` | `not images_only` | Images are the point; videos are opt-in via `--include-videos` |
| `download_video_thumbnails` | `False` | Avoids a stray `.jpg` next to every video |
| `download_geotags`, `download_comments`, `save_metadata` | `False` | No sidecar files — the tool downloads pictures, not archives |
| `post_metadata_txt_pattern` | `""` | Suppresses the caption `.txt` instaloader writes by default |
| `max_connection_attempts` | `3` | Retry a rate-limited request instead of dying on the first 429/401 |
| `request_timeout` | `30.0` | Bounded wait rather than hanging |

The four `False` flags and the empty `post_metadata_txt_pattern` are all deliberate departures
from instaloader's defaults. Re-enabling any of them changes what lands on disk.

## Outputs and exit codes

Files: `<out>/<target>/YYYY-MM-DD_HH-MM-SS_<shortcode>.jpg`, where `<target>` is the profile
username, the post owner's username (for `--post`), or the literal `saved`. Carousel posts
write one file per slide with a `_1`, `_2`, … suffix before the extension. A video-only post
writes nothing unless `--include-videos` is set (then `.mp4`). Times in filenames and in the
`--since`/`--until` comparison are UTC. A file already on disk is skipped, so re-runs only
fetch what's missing, though the feed is still walked from the top. `--out` defaults to
`downloads`, which is gitignored.

| Exit code | Meaning | Source |
|---|---|---|
| 0 | Success | [main.py:186](../main.py#L186) |
| 1 | Private profile, profile not found, login required, or connection/rate-limit failure | [main.py:150](../main.py#L150), [173-181](../main.py#L173-L181) |
| 2 | Bad flags (argparse) | argparse default |
| 130 | Interrupted with Ctrl-C during fetch/download (not at the password prompt; see below) | [main.py:184](../main.py#L184) |

## Quirks and workarounds

Please don't "clean up" these without reading the reason.

| Quirk | Where | Why it is like that |
|---|---|---|
| `import getpass` sits inside `login()`, not at module top | [main.py:60](../main.py#L60) | Deliberately deferred: it is only needed on the interactive password path. Ruff's selected rules permit this; don't hoist it. |
| `raise ... from None` on a bad date | [main.py:78](../main.py#L78) | Suppresses the chained `ValueError`, so a user typing `--since 2025-13-99` sees one clean argparse message instead of a traceback. Required by ruff `B904`. |
| `ap.error(...)` is called as a statement, not returned | [main.py:129](../main.py#L129) | `ArgumentParser.error` is typed `NoReturn`; `return ap.error(...)` type-checks badly and reads as if it returned a value. |
| The `try: import instaloader` guard is kept even though uv guarantees the dependency | [main.py:27-30](../main.py#L27-L30) | Gives a one-line "Run: uv sync" instead of a traceback when someone runs `python main.py` with a bare system interpreter. |
| `--until` uses `continue`, `--since` uses `break` | [main.py:102](../main.py#L102), [105](../main.py#L105) | Profile feeds arrive newest-first: posts newer than `--until` must be skipped individually, but the first post older than `--since` means everything after it is older too, so the loop can stop. See the limitation below. |
| Naive datetimes on both sides of the date comparison | [main.py:74](../main.py#L74) vs instaloader's `Post.date_utc` | `parse_date` returns a naive datetime and `date_utc` is built with `datetime.utcfromtimestamp()`, also naive. The comparison only works because *both* are naive UTC. If instaloader ever returns aware datetimes, `download_posts` raises `TypeError`. |

## Known limitations

| Limitation | Impact | Workaround |
|---|---|---|
| `--saved --since` can stop early and miss posts | `download_posts()` breaks on the first post older than `--since` ([main.py:103-105](../main.py#L103-L105)) because profile feeds are newest-first. The same function serves `get_saved_posts()`, which is ordered by when you *saved* a post, not when it was posted — so an old post saved recently can end the loop prematurely. | Use `--saved` with `--limit` instead of `--since`, or filter afterwards. Fix planned: [ROADMAP P1](ROADMAP.md#p1-correct-filters-and-no-tracebacks). |
| A pinned post can make `--profile --since` download nothing | Profiles can pin up to 3 posts to the top of the feed. If one is older than `--since`, the same `break` fires on the first post. Reproduced offline with stub posts: 0 of 2 matching posts downloaded. instaloader's own loop guards against this with `possibly_pinned=3`; ours doesn't. | Drop `--since` and use `--limit`, or use `--until` alone. Fix planned: [ROADMAP P1](ROADMAP.md#p1-correct-filters-and-no-tracebacks). |
| `--until` excludes its own day | `parse_date` returns midnight, and `download_posts()` skips `date_utc > until` ([main.py:101](../main.py#L101)), so `--until 2025-01-31` drops everything posted on the 31st after 00:00 UTC. The help text and README say "on/before". | Pass the following day. Fix planned: [ROADMAP P1](ROADMAP.md#p1-correct-filters-and-no-tracebacks). |
| Some failures still print a traceback | `dest.mkdir()` and `login()` run before the `try` ([main.py:131-137](../main.py#L131-L137)), so an unwritable `--out` (`OSError`), a wrong password or 2FA code (`BadCredentialsException`), other `LoginException`s, connection errors during login, and Ctrl-C at the password prompt all escape `main()`. Inside the `try`, only four exception types are caught. `BadResponseException` (e.g. a mistyped `--post` shortcode), `QueryReturnedBadRequestException`, `QueryReturnedForbiddenException`, and `PostChangedException` aren't subclasses of any of them. | Read the last line of the traceback; it is usually self-explanatory. Fix planned: [ROADMAP P1](ROADMAP.md#p1-correct-filters-and-no-tracebacks). |
| "Downloaded N post(s)" and `--limit` count attempts, not files | `download_posts()` increments for every post handed to `download_post()` ([main.py:106-107](../main.py#L106-L107)), including posts whose files were already on disk and video-only posts that write nothing in images-only mode. | Check the output folder for the real count. See [ROADMAP P2](ROADMAP.md#p2-day-to-day-usability). |
| `--limit 0` means unlimited | `if limit and ...` treats 0 as "no limit"; a negative limit downloads one post. No validation in argparse. | Pass a positive number. |
| A stale cached session isn't detected | `login()` returns as soon as `load_session_from_file` succeeds ([main.py:53-56](../main.py#L53-L56)), without checking the cookies still work, so an expired session never falls back to the password prompt. | Delete `~/.config/instaloader/session-<username>` and re-run. |
| A URL with `?` straight after the shortcode isn't parsed | `shortcode_from_url` splits on `/` only, so `.../p/ABC?img_index=2` yields `ABC?img_index=2`. `.../p/ABC/?igsh=…` (the usual share-link form) is fine. | Trim the query string, or pass the bare shortcode. |
| Session directory isn't `0700` | `login()` creates `~/.config/instaloader` itself ([main.py:69](../main.py#L69)), so instaloader skips its `chmod 0700` on the directory. The session file is still written `0600`. | `chmod 700 ~/.config/instaloader`. |
| Anonymous access is heavily rate-limited | `--profile` without `--login` frequently returns `401 "Please wait a few minutes before you try again."` even for public profiles. Observed repeatedly on 2026-09-30. The tool retries 3× then exits 1 with a readable message. | Pass `--login <username>`; keep runs small with `--limit`. |
| `--post` silently ignores `--limit`, `--since`, `--until` | Those flags only feed `download_posts()`, which the single-post path does not call. No warning is printed. | Nothing needed; just know they have no effect there. |
| `profile.is_private and not profile.followed_by_viewer` ([main.py:148](../main.py#L148)) | `followed_by_viewer` is only meaningful when logged in, so the early, friendly "private profile" check effectively requires `--login`. Anonymously you get a less specific error instead. | Use `--login`. |
| instaloader calls `datetime.utcfromtimestamp()`, deprecated in Python 3.12 | Silent today (DeprecationWarning is hidden by default), but it will break when Python removes it, and switching to aware datetimes upstream would break our date comparison. | Watch on Python upgrades; run with `-W error::DeprecationWarning` to see it. |
| No automated tests | Every change is verified by hand. | See the checklist in [DEVELOPMENT.md](DEVELOPMENT.md#manual-verification-checklist). |

## Extension points

- **A new CLI flag** → add the `ap.add_argument` in `main()` near the related flags, thread the
  value to whichever function consumes it, then document it in the README options table.
  Full recipe: [DEVELOPMENT.md](DEVELOPMENT.md#adding-a-new-flag).
- **A new download source** (e.g. hashtag, location) → add a member to the mutually exclusive
  group in `main()`, then a branch in the `try` block that obtains an iterable of posts and
  hands it to `download_posts()`. Reuse `download_posts()`; don't write a second loop.
- **Changing what lands on disk** → `build_loader()` only. All instaloader behaviour is
  centralised there, so nothing else needs touching.
- **A new handled error** → add an `except instaloader.exceptions.X` clause in `main()`, print
  a one-line hint to `stderr`, and return a non-zero code. Keep the existing style: actionable
  advice, no traceback.

## Decisions

Short ADRs. All were taken on 2026-09-30 while converting the project to uv, unless noted.
Append new entries; mark superseded ones rather than rewriting them.

### ADR-1: Manage the project with uv
*2026-09-30 · Accepted*

**Context.** The script assumed a globally installed `instaloader` and told users to run
`pip install instaloader`. There was no manifest, no lockfile, and no pinned interpreter; the
system Python on this machine is 3.9.6.
**Decision.** Adopt uv: `pyproject.toml` + committed `uv.lock` + `.python-version` pinned to
3.12. Runtime dependency `instaloader>=4.15.3`; dev group `ruff`, `ty`.
**Consequences.** Reproducible installs and no dependence on system Python, at the cost of
requiring uv to run the tool. `uv run main.py` becomes the canonical invocation.

### ADR-2: Flat layout, not a package
*2026-09-30 · Accepted*

**Context.** For a single-file CLI, the options were a `src/ig_downloader/` package with a
`[project.scripts]` entry point, or keeping one script at the repo root.
**Decision.** Flat layout. `main.py` at the root, no build backend, no console-script entry
point.
**Consequences.** Minimal structure for ~190 lines, and no import-path churn. The trade-off:
no `uv tool install .` and no `ig-download` command on `PATH` — you invoke it as
`uv run main.py`. Revisit if the script ever splits into modules.

### ADR-3: Name the entry point `main.py`
*2026-09-30 · Accepted*

**Context.** The file was `ig_download.py`. `uv init` generates a `main.py` stub by
convention, which would have sat beside it as dead code.
**Decision.** `git mv ig_download.py main.py`, then scaffold with `uv init --bare` so no stub
is generated at all. The rename went through git, so history follows the file.
**Consequences.** Matches uv's convention and leaves exactly one entry point. Any external
reference to `ig_download.py` breaks; `git log --follow main.py` still shows full history.

### ADR-4: Pin Python 3.12
*2026-09-30 · Accepted*

**Context.** instaloader supports `>=3.9`. The code needs nothing newer than 3.10 (`X | None`
unions). 3.12.13 was already present in uv's managed Pythons, so pinning it downloads nothing.
**Decision.** `requires-python = ">=3.12"`, `.python-version` = `3.12`.
**Consequences.** Modern syntax is available without `__future__` imports. Note that
instaloader's use of the deprecated `datetime.utcfromtimestamp()` is visible on 3.12; see
Known limitations before moving to a newer Python.

### ADR-5: ruff and ty, no pytest
*2026-09-30 · Accepted*

**Context.** The project needed lint/format and type-check config. A test suite was considered
and explicitly declined for now.
**Decision.** ruff (lint + format) and ty (type check) as dev dependencies, configured in
`pyproject.toml`. Lint selection: `E`, `F`, `I`, `UP`, `B`, `SIM`. No test framework.
**Consequences.** Style and types are enforced cheaply; correctness rests on manual
verification. `parse_date` and `shortcode_from_url` are the obvious first targets if tests
are added later.

### ADR-6: `line-length = 100`
*2026-09-30 · Accepted*

**Context.** ruff's default is 88. The longest line in the existing script was exactly 100
characters, so the default would have reflowed five lines of otherwise-fine code.
**Decision.** Set `line-length = 100`.
**Consequences.** The formatting diff stayed limited to two call sites that ruff's magic
trailing comma expanded. Lines run slightly wider than the community default.

### ADR-7: Commit `uv.lock`
*2026-09-30 · Accepted*

**Context.** Lockfiles are committed for applications and usually not for libraries.
**Decision.** Commit `uv.lock`; gitignore `.venv/`, `downloads/`, `.ruff_cache/`, `.ty_cache/`.
**Consequences.** `uv sync` reproduces an identical environment. Dependency bumps show up as
lockfile diffs to review.

### ADR-8: Images only by default
*Pre-dates the uv conversion (2026-09-26) · Accepted*

**Context.** instaloader downloads videos, thumbnails, geotags, comments, and metadata sidecars
by default. Reason not recorded in commit history, but the code and docstring are unambiguous
about intent.
**Decision.** Turn all of that off in `build_loader()`; videos are opt-in via
`--include-videos`.
**Consequences.** Output directories contain just the pictures. Anyone wanting a full archive
must change `build_loader()`.
