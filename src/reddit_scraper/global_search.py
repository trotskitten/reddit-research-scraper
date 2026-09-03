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
DEFAULT_BATCH_SIZE = 5
DEFAULT_SEARCH_LIMIT = 250


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


def _batch_terms(terms: list[str], batch_size: int) -> list[list[str]]:
    """Split configured terms into stable source-order batches."""

    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    return [terms[index:index + batch_size] for index in range(0, len(terms), batch_size)]


def search_reddit_by_keywords(
    reddit: praw.Reddit,
    pain_keywords: Iterable[str],
    tools: Iterable[str],
    lookback_hours: int,
    *,
    case_sensitive: bool = False,
    now_utc: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    search_limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[dict[str, object]]:
    """Search all Reddit for recent posts satisfying pain + tool matching.

    The configured pain vocabulary is split into small source-order batches.
    Each batch is searched independently against the full tool vocabulary:

        (pain1 OR pain2 OR ...) AND (tool1 OR tool2 OR ...)

    With the current 35 pain terms and the default batch size of five, this
    produces seven Reddit searches. Each search requests at most 250 newest
    candidates. Reddit search is used only for discovery: every returned post is
    restricted to the configured lookback window and locally verified against
    the FULL pain and tool vocabularies. Results are deduplicated by Reddit ID
    across all batches.
    """

    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be greater than zero")
    if search_limit <= 0:
        raise ValueError("search_limit must be greater than zero")

    current_time = now_utc or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    pain_terms = [term for term in pain_keywords if term]
    tool_terms = [term for term in tools if term]
    if not pain_terms:
        raise ValueError("At least one pain keyword is required")
    if not tool_terms:
        raise ValueError("At least one tool keyword is required")

    pain_batches = _batch_terms(pain_terms, batch_size)
    cutoff_timestamp = (
        current_time.astimezone(timezone.utc) - timedelta(hours=lookback_hours)
    ).timestamp()

    all_subreddits = reddit.subreddit("all")
    matched_posts: list[dict[str, object]] = []
    seen_ids: set[str] = set()

    for batch_number, pain_batch in enumerate(pain_batches, start=1):
        query = build_global_search_query(pain_batch, tool_terms)
        raw_count = 0
        within_lookback_count = 0
        new_match_count = 0

        for submission in all_subreddits.search(
            query,
            sort="new",
            syntax="lucene",
            time_filter="day",
            limit=search_limit,
        ):
            raw_count += 1
            if float(submission.created_utc) < cutoff_timestamp:
                continue

            within_lookback_count += 1
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
            new_match_count += 1

        LOGGER.info(
            "Global search batch %d/%d: pains=%s raw=%d within_lookback=%d new_exact_matches=%d",
            batch_number,
            len(pain_batches),
            pain_batch,
            raw_count,
            within_lookback_count,
            new_match_count,
        )

    LOGGER.info(
        "Global Reddit batched search found %d distinct pain+tool matches across %d queries",
        len(matched_posts),
        len(pain_batches),
    )
    return matched_posts
