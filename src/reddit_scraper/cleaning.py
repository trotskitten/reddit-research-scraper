"""Reddit post cleaning and dataset schema normalization layer."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

DATASET_COLUMNS = (
    "subreddit",
    "id",
    "title",
    "author",
    "created_utc",
    "created_iso",
    "url",
    "selftext",
)


def clean_post(post: dict[str, object]) -> dict[str, object]:
    """Convert one matched scraper post to the existing Drive dataset schema.

    Matching metadata such as ``matched_pain_keywords`` and ``matched_tools`` is
    intentionally discarded. The body text is preserved exactly so downstream
    exact-text deduplication compares the original Reddit content.
    """

    post_id = str(post.get("post_id") or "")
    subreddit = str(post.get("subreddit") or "")
    title = str(post.get("title") or "")
    body = str(post.get("text") or "")
    author_value = post.get("author")
    author = "" if author_value is None else str(author_value)
    url = str(post.get("url") or "")

    if not post_id:
        raise ValueError("post_id is required")
    if not subreddit:
        raise ValueError("subreddit is required")

    created_value = post.get("created_utc")
    if created_value is None:
        raise ValueError("created_utc is required")

    try:
        created_utc = float(created_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("created_utc must be numeric") from exc

    created_iso = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

    return {
        "subreddit": subreddit,
        "id": post_id,
        "title": title,
        "author": author,
        "created_utc": created_utc,
        "created_iso": created_iso,
        "url": url,
        "selftext": body,
    }


def clean_posts(posts: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Convert matched posts to rows compatible with the existing dataset."""

    return [clean_post(post) for post in posts]
