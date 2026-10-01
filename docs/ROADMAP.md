# Roadmap and Backlog

What to work on next, each item with why it matters and where it goes in the code. Take one
item per branch (`fix/…`, `feat/…`). When it ships, tick it under **Done**, flip its status in
the [PRD](PRD.md#6-functional-requirements), remove the matching row from
[Known limitations](ARCHITECTURE.md#known-limitations), and add an ADR in
[ARCHITECTURE.md](ARCHITECTURE.md#decisions) if the choice could be questioned later.

Line numbers refer to `main.py` as of 2026-10-01 and will drift. Search for the function name
if they no longer match.

## Done (0.1.0)

- [x] Initial script: profile / single post / saved sources, `--limit`/`--since`/`--until`,
  cached login with 2FA, images-only defaults. `ebb211c` (2026-09-26).
- [x] Renamed `ig_download.py` → `main.py`. `f44ebd8` (2026-09-30).
- [x] Converted to uv: `pyproject.toml`, committed `uv.lock`, Python 3.12 pin, ruff + ty,
  type annotations on `download_posts`, README. `f6bdb4e` (2026-09-30).
- [x] Architecture/decisions, development guide, CLAUDE.md. `0c12635` (2026-09-30).
- [x] PRD, this roadmap, and docs corrected against the code (2026-10-01).

## Next up

### P1: Correct filters and no tracebacks

These are bugs against behaviour the help text and README already promise. Each was
confirmed offline by feeding stub posts to `download_posts()`.

| Item | Why | Where / notes |
|---|---|---|
| **Make `--until` include its own day** | `--until 2025-01-31` parses to `2025-01-31 00:00`, so every post made later that day is skipped. Help text says "on/before". | `download_posts()` [main.py:101](../main.py#L101). Compare against `until + timedelta(days=1)` (exclusive), or add the day in `main()`. Leave `parse_date()` alone: `--since` shares it and is correct. |
| **Don't let pinned posts end `--since` early** | A profile can pin up to 3 posts to the top of its feed. If a pinned post is older than `--since`, the newest-first `break` fires on post #1 and the run downloads 0 posts. | `download_posts()` [main.py:103-105](../main.py#L103-L105). Mirror instaloader's own guard: `posts_download_loop(..., possibly_pinned=3)` only lets the takewhile stop the loop after the first 3 posts. Don't rely on `Post.is_pinned`: its docstring says it "now likely returns always false". |
| **Don't short-circuit `--since` on `--saved`** | The saved feed is ordered by save time, not post date, so the `break` can drop older posts saved recently. | Same branch. Add a fully annotated parameter such as `newest_first: bool` (True for `get_posts()`, False for `get_saved_posts()`), and `continue` instead of `break` when False. Best done in one change with the pinned-post fix. |
| **Close the traceback gaps in `main()`** | CLAUDE.md promises no exception escapes `main()`, but several do. A wrong password raises `BadCredentialsException`. A bad `--post` shortcode raises `BadResponseException` ("Fetching Post metadata failed."). An unwritable `--out` raises `OSError`. Ctrl-C at the password prompt raises `KeyboardInterrupt`. All are outside the `try` or not subclasses of the four caught types. | Move `dest.mkdir(...)` and `login(...)` ([main.py:131-137](../main.py#L131-L137)) inside the `try`. Add `except instaloader.exceptions.LoginException` (parent of `BadCredentialsException`), `except OSError`, and a last-resort `except instaloader.exceptions.InstaloaderException` *after* the specific clauses ([main.py:173-184](../main.py#L173-L184)). Keep one actionable line and exit 1. |
| **Regression tests for the above** | The four fixes are easy to break again silently, and all can be tested without network. | Needs ADR-5 revisited (append an ADR rather than editing it). `uv add --dev pytest`, `tests/test_main.py`. Stub loader + stub posts with `date_utc`, as described in [DEVELOPMENT.md](DEVELOPMENT.md#testing-strategy). |

### P2: Day-to-day usability

| Item | Why | Where / notes |
|---|---|---|
| **Detect an expired cached session** | `load_session_from_file` only reads cookies and never checks them, so a stale session fails later with a login or connection error instead of re-prompting. The only fix today is deleting the file by hand. | `login()` [main.py:53-58](../main.py#L53-L58). After loading, call `loader.test_login()`: it returns the username, or `None` when the session is dead. On `None`, fall through to the password prompt. Costs one request per run. |
| **Report honest counts** | `download_posts()` counts every post it passes to `download_post()`, including posts whose files already existed and video-only posts that wrote nothing in images-only mode. The summary line overstates, and `--limit 20` on a reel-heavy profile can produce far fewer than 20 images. | `download_posts()` [main.py:106-107](../main.py#L106-L107). `download_post()` returns False when the file was already there, but it returns True for a video-only post in images-only mode even though it wrote nothing. Detecting that case needs a separate `post.typename == "GraphVideo"` check. Answer [PRD open question 2](PRD.md#10-open-questions) first: should `--limit` count posts or new downloads? Update the three `print` summaries. |
| **Reject `--limit` ≤ 0** | `--limit 0` is falsy and means unlimited; `--limit -1` downloads one post. | [main.py:122](../main.py#L122). Use a positive-int `type=` function in the style of `parse_date()` (raise `ArgumentTypeError ... from None`) so it exits 2. |
| **Strip query strings in `shortcode_from_url`** | `.../p/ABC?img_index=2` (no slash before `?`) yields shortcode `ABC?img_index=2`, and the fetch fails. | [main.py:81-88](../main.py#L81-L88). Split `urllib.parse.urlsplit(url).path` instead of the raw string; keep the bare-shortcode fallback. |
| **Warn when filters are passed with `--post`** | `--limit/--since/--until` are silently ignored there. | Right after the `--saved` check, [main.py:128](../main.py#L128). A stderr note, not `ap.error` (it isn't wrong, just a no-op). See [PRD open question 5](PRD.md#10-open-questions). |

### P3: Nice to have

- **CI.** A GitHub Actions workflow on `gayashan4lk/ig-downloader` running `uv sync --locked`,
  `ruff format --check`, `ruff check`, `ty check main.py` (and tests, once they exist). No
  network steps.
- **Session directory permissions.** [main.py:69](../main.py#L69) creates
  `~/.config/instaloader` before instaloader does, which skips instaloader's
  `chmod 0700` on the directory (it only chmods a directory it creates). The session *file* is
  still `0600`, so the impact is small. Letting `save_session_to_file` create the directory
  fixes it for new machines; existing directories need a manual `chmod 700`.
- **Local-time dates** for filters and filenames, if [PRD open question 3](PRD.md#10-open-questions)
  goes that way. instaloader exposes `Post.date_local`.

## Known limitations

The canonical table, with impact and workaround for each, lives in
[ARCHITECTURE.md → Known limitations](ARCHITECTURE.md#known-limitations), so it stays next to
the code description. Every P1/P2 item above removes one row from it.

## Maintenance tasks (recurring)

- **Upgrade instaloader when Instagram breaks it.** That happens without warning.
  `uv lock --upgrade-package instaloader && uv sync`, run the gate and offline checks, then the
  maintainer runs a real logged-in download by hand. Several statements in these docs are
  specific to 4.15.3; re-check them after an upgrade:
  - the exception hierarchy (which types subclass `ConnectionException`)
  - `possibly_pinned=3` in `posts_download_loop`
  - `datetime.utcfromtimestamp()` in `Post.date_utc`
  - the carousel `_1`, `_2` filename suffixes
- **Before moving past Python 3.12**, grep instaloader for `utcfromtimestamp`. If it has
  switched to timezone-aware datetimes, `parse_date()` must return aware UTC too, or the
  comparisons in `download_posts()` raise `TypeError`
  ([quirk](ARCHITECTURE.md#quirks-and-workarounds)).
- **ty is pre-1.0** (0.0.84 locked). Upgrades can add new diagnostics. Fix them rather than
  adding ignores, and never ignore `instaloader` imports (CLAUDE.md).
