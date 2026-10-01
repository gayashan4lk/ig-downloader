#!/usr/bin/env python3
"""
Download Instagram images.

Setup: uv sync

Examples:
    # Public profile, newest 20 posts, images only
    uv run main.py --profile natgeo --limit 20

    # A single post
    uv run main.py --post https://www.instagram.com/p/C1abcdefg/

    # Your own saved posts (needs login)
    uv run main.py --saved --login yourusername

    # Posts from a profile after a date
    uv run main.py --profile natgeo --since 2025-01-01
"""

import argparse
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

try:
    import instaloader
except ImportError:
    sys.exit("instaloader is not installed. Run: uv sync")


def build_loader(dest: Path, images_only: bool, saved: bool) -> instaloader.Instaloader:
    # One folder per post: <out>/<user>/<date>_<mediaid>/. Saved posts are grouped by
    # owner under <out>/saved/, since the saved feed mixes many users.
    owner_dir = dest / "saved" / "{owner_username}" if saved else dest / "{target}"
    return instaloader.Instaloader(
        dirname_pattern=str(owner_dir / "{date_utc:%Y-%m-%d_%H-%M-%S}_{mediaid}"),
        filename_pattern="{date_utc:%Y-%m-%d_%H-%M-%S}_{shortcode}",
        download_videos=not images_only,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        # Back off and retry instead of dying on a 429
        max_connection_attempts=3,
        request_timeout=30.0,
    )


def login(loader: instaloader.Instaloader, username: str) -> None:
    """Log in, reusing a cached session file so you don't re-auth every run."""
    session_file = Path.home() / ".config" / "instaloader" / f"session-{username}"
    try:
        loader.load_session_from_file(username, str(session_file))
        print(f"Loaded cached session for {username}")
        return
    except FileNotFoundError:
        pass

    import getpass

    password = getpass.getpass(f"Password for {username}: ")
    try:
        loader.login(username, password)
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        code = input("Two-factor code: ").strip()
        loader.two_factor_login(code)

    session_file.parent.mkdir(parents=True, exist_ok=True)
    loader.save_session_to_file(str(session_file))
    print(f"Session saved to {session_file}")


def parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Use YYYY-MM-DD, got {value!r}") from None


def shortcode_from_url(url: str) -> str:
    """Pull the shortcode out of a /p/, /reel/, or /tv/ URL."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    for marker in ("p", "reel", "reels", "tv"):
        if marker in parts:
            return parts[parts.index(marker) + 1]
    # Maybe they just passed the bare shortcode
    return parts[-1]


def download_posts(
    loader: instaloader.Instaloader,
    posts: Iterable[instaloader.Post],
    target: str,
    limit: int | None,
    since: datetime | None,
    until: datetime | None,
) -> int:
    count = 0
    for post in posts:
        if until and post.date_utc > until:
            continue
        if since and post.date_utc < since:
            # Profile feeds are newest-first, so we can stop here
            break
        loader.download_post(post, target=target)
        count += 1
        if limit and count >= limit:
            break
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description="Download images from Instagram.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--profile", help="Username whose posts to download")
    src.add_argument("--post", help="URL or shortcode of a single post")
    src.add_argument("--saved", action="store_true", help="Your saved posts (requires --login)")

    ap.add_argument("--login", help="Your Instagram username, for private/saved content")
    ap.add_argument("--out", default="downloads", help="Output directory (default: downloads)")
    ap.add_argument("--limit", type=int, help="Stop after N posts")
    ap.add_argument("--since", type=parse_date, help="Only posts on/after YYYY-MM-DD")
    ap.add_argument("--until", type=parse_date, help="Only posts on/before YYYY-MM-DD")
    ap.add_argument("--include-videos", action="store_true", help="Also download videos")
    args = ap.parse_args()

    if args.saved and not args.login:
        ap.error("--saved requires --login")

    dest = Path(args.out).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    loader = build_loader(dest, images_only=not args.include_videos, saved=args.saved)

    if args.login:
        login(loader, args.login)

    try:
        if args.post:
            code = shortcode_from_url(args.post)
            post = instaloader.Post.from_shortcode(loader.context, code)
            loader.download_post(post, target=post.owner_username)
            print(f"Downloaded 1 post to {dest}")

        elif args.profile:
            profile = instaloader.Profile.from_username(loader.context, args.profile)
            if profile.is_private and not profile.followed_by_viewer:
                print(f"{args.profile} is private and you don't follow them.", file=sys.stderr)
                return 1
            n = download_posts(
                loader,
                profile.get_posts(),
                profile.username,
                args.limit,
                args.since,
                args.until,
            )
            print(f"Downloaded {n} post(s) to {dest / profile.username}")

        else:  # --saved
            profile = instaloader.Profile.from_username(loader.context, args.login)
            n = download_posts(
                loader,
                profile.get_saved_posts(),
                "saved",
                args.limit,
                args.since,
                args.until,
            )
            print(f"Downloaded {n} saved post(s) to {dest / 'saved'}")

    except instaloader.exceptions.ProfileNotExistsException:
        print("That profile doesn't exist.", file=sys.stderr)
        return 1
    except instaloader.exceptions.LoginRequiredException:
        print("Instagram wants a login for this. Re-run with --login <username>.", file=sys.stderr)
        return 1
    except instaloader.exceptions.ConnectionException as e:
        print(f"Connection/rate-limit problem: {e}\nWait a while before retrying.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    sys.exit(main())
