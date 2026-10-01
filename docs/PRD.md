# Product Requirements: ig-downloader (`main.py`)

| | |
|---|---|
| **Status** | 0.1.0: three sources (profile, single post, saved), date/count filters, cached login. No automated tests. |
| **Owner** | gayashan4lk |
| **Last updated** | 2026-10-01 |
| **Related** | [Architecture + decisions](ARCHITECTURE.md) · [Roadmap](ROADMAP.md) · [Development guide](DEVELOPMENT.md) |

## 1. Summary

A personal command-line tool that downloads the **pictures** from Instagram posts the user can
already see: a profile's feed, one post, or their own saved collection. It is a thin wrapper
over [instaloader](https://instaloader.github.io/) that sets images-only, no-sidecar defaults,
so the output folder holds only images.

## 2. Problem

- Instagram has no "download these photos" button. Saving images one at a time from the app
  or browser is slow and loses the post date.
- instaloader can do the work, but its defaults build a full archive: videos, video
  thumbnails, caption `.txt` files, JSON metadata, geotags, comments. Getting plain images
  takes a long list of flags each time.
- A saved collection is private to the account, so a tool has to log in to reach it. Typing
  a password (and 2FA code) on every run is tedious.

## 3. Goals

1. **One command per job:** profile, single post, or saved collection, each with a single
   flag.
2. **Images only by default:** no videos, thumbnails, captions, metadata, geotags, or
   comments unless explicitly asked for (videos only, via `--include-videos`).
3. **Sortable output:** one folder per profile, one folder per post inside it
   (`YYYY-MM-DD_HH-MM-SS_<mediaid>`), and files named `YYYY-MM-DD_HH-MM-SS_<shortcode>`.
4. **Log in once:** reuse a cached session on later runs.
5. **Fail politely:** expected failures (rate limit, private profile, missing login) print one
   actionable line and exit non-zero, with no traceback.
6. **Zero setup beyond uv:** `uv sync` provides the interpreter and dependencies.

## 4. Non-goals

- **Content the logged-in user can't see.** No private-profile workarounds, no scraping
  behind login walls the account hasn't passed.
- **Bulk harvesting.** One profile, post, or collection per run. No lists of accounts, no
  crawling followers or related accounts.
- **Getting around rate limits.** The 3-attempt cap and 30 s timeout in `build_loader()` are a
  deliberate ceiling. No proxy rotation, no aggressive retries, no multiple accounts.
- **Archival fidelity.** Captions, comments, metadata, and geotags are deliberately dropped
  ([ADR-8](ARCHITECTURE.md#adr-8-images-only-by-default)). Use instaloader directly for a full
  archive.
- **Installable command / package.** No `ig-download` on `PATH`; it runs as `uv run main.py`
  ([ADR-2](ARCHITECTURE.md#adr-2-flat-layout-not-a-package)).
- **GUI, scheduling, or a server.** It is an interactive, run-on-demand CLI.

## 5. Users

| Persona | Needs |
|---|---|
| **The maintainer (primary)** | Grab a recent batch of images from a public profile (`--profile X --limit N`), or a date range of them |
| **Saving a single post** | Paste a post or reel URL from the share sheet and get its images (`--post <url>`) |
| **Backing up own saves** | Pull the images from their saved collection, logging in once (`--saved --login me`) |

It is a personal tool. There are no other users to support and no compatibility promises.

## 6. Functional requirements

Status legend: ✅ shipped · ⚠️ shipped with a known defect · 🔜 planned · ❌ out of scope

### 6.1 Sources

| ID | Requirement | Status |
|---|---|---|
| S1 | `--profile <user>` downloads that profile's posts, newest first | ✅ |
| S2 | `--post <url-or-shortcode>` downloads one post; accepts `/p/`, `/reel/`, `/reels/`, `/tv/` URLs or a bare shortcode | ⚠️ a query string with no slash before it (`/p/ABC?img_index=2`) becomes part of the shortcode |
| S3 | `--saved` downloads the logged-in user's saved posts; requires `--login` (exit 2 otherwise) | ✅ |
| S4 | Exactly one source per run, enforced by argparse (exit 2) | ✅ |
| S5 | A private profile the viewer doesn't follow is refused early with a clear message | ⚠️ only reliable with `--login`: `followed_by_viewer` is meaningless anonymously |
| S6 | Hashtag, location, stories, highlights sources | ❌ not planned; see [open question 4](#10-open-questions) |

### 6.2 Filters

| ID | Requirement | Status |
|---|---|---|
| F1 | `--limit N` stops after N posts | ⚠️ `--limit 0` means unlimited and negative values download 1; posts that write no file (video-only, already present) still count |
| F2 | `--since YYYY-MM-DD` keeps posts on or after the date (UTC) | ⚠️ stops early when an old pinned post leads a profile feed, and on `--saved` (save-ordered feed) |
| F3 | `--until YYYY-MM-DD` keeps posts on or before the date (UTC) | ⚠️ posts made *on* the `--until` day are excluded (the date is compared as 00:00 UTC) |
| F4 | Bad dates fail during argument parsing, before any network call (exit 2) | ✅ |
| F5 | Filters apply to `--profile` and `--saved`; `--post` ignores them | ✅ (silently, with no warning) |

### 6.3 Output

| ID | Requirement | Status |
|---|---|---|
| O1 | Images only by default; no thumbnails, captions, JSON, geotags, or comments | ✅ |
| O2 | `--include-videos` also downloads videos | ✅ |
| O3 | Each post gets its own folder: `<out>/<username>/YYYY-MM-DD_HH-MM-SS_<mediaid>/YYYY-MM-DD_HH-MM-SS_<shortcode>.jpg`; carousel slides add `_1`, `_2`, …; `--saved` posts go under `<out>/saved/<owner>/` ([ADR-9](ARCHITECTURE.md#adr-9-one-folder-per-post)) | ✅ |
| O4 | `--out` sets the root directory (default `downloads/`, gitignored), created if missing | ✅ |
| O5 | Re-running skips files already on disk | ✅ (instaloader behaviour; the feed is still walked from the top) |
| O6 | The final "Downloaded N post(s)" line reports what was actually written | ⚠️ counts posts attempted, including skipped ones and video-only posts that produced no file |

### 6.4 Authentication

| ID | Requirement | Status |
|---|---|---|
| A1 | `--login <user>` prompts for a password with `getpass` | ✅ |
| A2 | Two-factor challenge prompts for a code | ✅ |
| A3 | Session cached at `~/.config/instaloader/session-<user>` and reused on later runs | ✅ |
| A4 | An expired cached session is detected and falls back to the password prompt | 🔜 ([roadmap](ROADMAP.md#p2-day-to-day-usability)); today a stale session fails later with a login/connection error |

### 6.5 Shared behaviour: errors and exit codes

| ID | Requirement | Status |
|---|---|---|
| E1 | Every expected failure prints one actionable line to stderr; no tracebacks | ⚠️ the login path, a bad `--post` shortcode, and filesystem errors still raise tracebacks ([details](ARCHITECTURE.md#known-limitations)) |
| E2 | Exit codes: 0 success, 1 runtime/network failure, 2 bad flags, 130 Ctrl-C | ⚠️ Ctrl-C at the password prompt shows a traceback instead of "Stopped." |
| E3 | A failing request gets at most 3 attempts with a 30 s timeout each, then the run exits 1 with advice to wait | ✅ |

## 7. Non-functional requirements

| Area | Requirement |
|---|---|
| Platform | macOS/Linux shell. Windows is untested. |
| Runtime | Python 3.12 (`.python-version`, `requires-python = ">=3.12"`), provided by uv. Never the system Python (3.9.6 on the maintainer's machine). |
| Dependencies | One runtime dependency, `instaloader>=4.15.3` (4.15.3 locked). Dev: `ruff`, `ty`. `uv.lock` is committed. |
| Code quality | `ruff format --check`, `ruff check` (`E,F,I,UP,B,SIM`, line length 100), and `ty check main.py` all pass |
| Testability | No test suite ([ADR-5](ARCHITECTURE.md#adr-5-ruff-and-ty-no-pytest)). `download_posts()` takes its loader and post iterable as parameters so a future suite can stub both without network. |
| Security / privacy | No secrets in the repo; the password is never stored. The session file holds live cookies (instaloader writes it `0600`). Treat it as a credential. |
| Politeness | Single-threaded, sequential downloads with bounded retries. |

## 8. Constraints and risks

| Risk | Impact | Mitigation |
|---|---|---|
| Instagram changes its private web API | instaloader breaks; downloads fail with connection or bad-response errors | Upgrade instaloader (`uv lock --upgrade-package instaloader`), then the maintainer re-tests by hand ([maintenance](ROADMAP.md#maintenance-tasks-recurring)) |
| Aggressive rate limiting, especially anonymous | Anonymous `--profile` was unusable on 2026-09-30 (repeated `401 "Please wait a few minutes"`) | Use `--login`, keep `--limit` small, never retry in a loop |
| Account action against the logged-in user | Automated access can trigger checkpoints or temporary blocks on the maintainer's real account | Small runs; respect the retry ceiling; no parallelism |
| Terms of service and copyright | Instagram's terms restrict automated collection; downloaded images belong to their creators | Personal use only, content the user can already see (see [Non-goals](#4-non-goals)) |
| Session file leakage | Anyone with `session-<user>` can act as that account | Lives outside the repo in `~/.config`; file is `0600`; never commit or share it |
| Python deprecation | instaloader 4.15.3 uses `datetime.utcfromtimestamp()`, deprecated since 3.12 | Check before any Python upgrade ([limitation](ARCHITECTURE.md#known-limitations)) |

## 9. Success criteria

- The [offline checks](DEVELOPMENT.md#manual-verification-checklist) pass: `--help` renders,
  and the three bad-flag cases each exit 2 with a one-line message.
- The lint/format/type gate passes.
- A logged-in `--profile <user> --limit 2 --out /tmp/ig-smoke` run (by the maintainer) writes
  one folder per post containing only `.jpg` files named by date and shortcode, with no
  `.txt`/`.json` sidecars, and exits 0.
- A rate-limited run exits 1 with "Connection/rate-limit problem: …" and no traceback.

## 10. Open questions

1. **Tests.** ADR-5 declined a suite "for now". The ⚠️ items above are cheap to pin down with
   stubbed tests. Revisit? *Current default: no tests.*
2. **What does `--limit` count?** Posts examined, posts that produced a file, or image files?
   *Current default: posts examined, including skipped and video-only ones.*
3. **UTC or local dates?** `--since`/`--until` and filenames use UTC, so a post made late in
   the evening in a timezone ahead of UTC can land on the previous day. *Current default: UTC.*
4. **More sources** (hashtag, location, stories, highlights)? The download loop is ready for
   them, but none has been asked for, and hashtag/location feeds sit close to the "bulk
   harvesting" non-goal. *Current default: not planned.*
5. **Warn when filters are passed with `--post`?** *Current default: silently ignored.*
