# ig-downloader

A small command-line tool for downloading images from Instagram — a public profile's
posts, a single post, or your own saved collection. Wraps
[instaloader](https://instaloader.github.io/) with sensible defaults: images only,
no metadata sidecars, no comments, and filenames stamped with the post date.

## Setup

Requires [uv](https://docs.astral.sh/uv/). Everything else, including the Python
interpreter, is handled for you:

```sh
uv sync
```

## Usage

```sh
# Public profile, newest 20 posts, images only
uv run main.py --profile natgeo --limit 20

# A single post (URL or bare shortcode)
uv run main.py --post https://www.instagram.com/p/C1abcdefg/

# Your own saved posts (needs login)
uv run main.py --saved --login yourusername

# Posts from a profile on or after a date
uv run main.py --profile natgeo --since 2025-01-01
```

### Options

| Flag | Description |
| --- | --- |
| `--profile <user>` | Download a profile's posts |
| `--post <url>` | Download one post by URL or shortcode |
| `--saved` | Download your saved posts (requires `--login`) |
| `--login <user>` | Your Instagram username, for private or saved content |
| `--out <dir>` | Output directory (default: `downloads`) |
| `--limit <n>` | Stop after N posts |
| `--since <YYYY-MM-DD>` | Only posts on or after this date |
| `--until <YYYY-MM-DD>` | Only posts on or before this date (currently excludes the date itself, see [known limitations](docs/ARCHITECTURE.md#known-limitations)) |
| `--include-videos` | Also download videos (off by default) |

Exactly one of `--profile`, `--post`, or `--saved` is required.

Each post gets its own folder, grouped by profile:

```
downloads/
  natgeo/                                      # --profile natgeo, or a --post by natgeo
    2025-01-03_14-22-10_3301234567890123456/   # <post date>_<numeric media ID>
      2025-01-03_14-22-10_C1abcdefg_1.jpg      # carousel slides get _1, _2, …
      2025-01-03_14-22-10_C1abcdefg_2.jpg
      2025-01-03_14-22-10_C1abcdefg_3.mp4      # only with --include-videos
  saved/
    nasa/                                      # --saved, grouped by who posted it
      2024-11-20_08-00-00_3298765432109876543/
        2024-11-20_08-00-00_C2hijklmn.jpg
```

Dates and times are UTC. Downloads made before this layout existed (flat files directly in
`<out>/<user>/`) are left where they are. Re-running re-downloads those posts into the new
folders.

## Logging in

Private profiles you follow and your own saved posts need `--login <username>`. You'll
be prompted for your password (and a two-factor code if your account has 2FA enabled).
The session is then cached at `~/.config/instaloader/session-<username>` and reused on
later runs, so you only authenticate once.

## A note on rate limits

Instagram throttles aggressively. If you hit a rate limit the tool reports a
connection problem and exits rather than hammering the API — wait a while before
retrying, and prefer `--limit` to keep runs small.

## Development

```sh
uv run ruff format .      # format
uv run ruff check .       # lint
uv run ty check main.py   # type check
```

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | What the tool is for, goals and non-goals, requirements with shipped/known-defect status, risks, open questions |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the script works end to end, instaloader defaults, exit codes, quirks to leave alone, known limitations, and the decision log |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Prioritised backlog (each item with why and where in the code), and recurring maintenance |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Setup, daily commands, verification checklist, how to add a flag, conventions, troubleshooting |
| [CLAUDE.md](CLAUDE.md) | One-page brief for AI assistants working in this repo |
