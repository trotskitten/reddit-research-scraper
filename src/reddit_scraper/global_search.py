"""Global Reddit keyword-search retrieval.

The curated subreddit scraper intentionally does not use keyword filtering.
This module is the separate discovery path for finding posts anywhere on Reddit
that contain at least one configured pain term and at least one configured tool
term.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

import praw

from reddit_scraper.matcher import match_post
from reddit_scraper.scraper import submission_to_raw_post

LOGGER = logging.getLogger(__name__)


def _quote_search_term(term: str) -> str:
    """Quote one configured term for a Reddit/Lucene search query."""

    escaped = term.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_global_search_query(
    pain_keywords: Iterable[str],
    tools: Iterable[str],
) -> str:
    """Build one Reddit query: (pain1 OR pain2...) AND (tool1 OR tool2...)."""

    pain_terms = [term for term in pain_keywords if term]
    tool_terms = [term for term in tools if term]

    if not pain_terms:
        raise ValueError("At least one pain keyword is required")
    if not tool_terms:
        raise ValueError("At least one tool keyword is required")

    pain_expression = " OR ".join(_quote_search_term(term) for term in pain_terms)
    tool_expression = " OR ".join(_quote_search_term(term) for term in tool_terms)
    return f"({pain_expression}) AND ({tool_expression})"


def search_reddit_by_keywords(
    reddit: praw.Reddit,
    pain_keywords: Iterable[str],
    tools: Iterable[str],
    lookback_hours: int,
    *,
    case_sensitive: bool = False,
    now_utc: datetime | None = None,
) -> list[dict[str, object]]:
    """Search all Reddit for recent posts satisfying pain + tool matching.

    One server-side r/all search uses the full Boolean expression:

        (pain1 OR pain2 OR ...) AND (tool1 OR tool2 OR ...)

    Reddit search is used only for discovery. Every returned post is restricted
    to the configured lookback window and then locally verified with the same
    whole-word/phrase matcher used elsewhere in the project. This keeps the final
    qualification rule deterministic even if Reddit search behaves fuzzily.
    """

    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be greater than zero")

    current_time = now_utc or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    pain_terms = list(pain_keywords)
    tool_terms = list(tools)
    query = build_global_search_query(pain_terms, tool_terms)
    cutoff_timestamp = (
        current_time.astimezone(timezone.utc) - timedelta(hours=lookback_hours)
    ).timestamp()

    all_subreddits = reddit.subreddit("all")
    matched_posts: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for submission in all_subreddits.search(
        query,
        sort="new",
        syntax="lucene",
        time_filter="day",
        limit=None,
    ):
        if float(submission.created_utc) < cutoff_timestamp:
            continue

        raw_post = submission_to_raw_post(submission)
        matched_post = match_post(
            raw_post,
            pain_terms,
            tool_terms,
            case_sensitive=case_sensitive,
        )
        if matched_post is None:
            continue

        post_id = str(matched_post["post_id"])
        if post_id in seen_ids:
            continue

        seen_ids.add(post_id)
        matched_posts.append(matched_post)

    LOGGER.info(
        "Global Reddit Boolean search found %d pain+tool matches",
        len(matched_posts),
    )
    return matched_posts
