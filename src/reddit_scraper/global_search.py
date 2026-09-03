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


def build_tool_search_query(pain_keywords: Iterable[str], tool: str) -> str:
    """Build one global-search query for a tool plus any configured pain term.

    We issue one Reddit search per tool rather than one search for every
    pain×tool pair. The exact pain+tool rule is verified locally on every result,
    so Reddit search is used for candidate discovery rather than final matching.
    """

    pain_terms = [term for term in pain_keywords if term]
    if not pain_terms:
        raise ValueError("At least one pain keyword is required")
    if not tool:
        raise ValueError("tool must not be empty")

    pain_expression = " OR ".join(_quote_search_term(term) for term in pain_terms)
    return f"({pain_expression}) AND {_quote_search_term(tool)}"


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

    One server-side search is issued per configured tool using r/all, sorted by
    newest first and restricted by Reddit's one-day time filter. Results are then
    restricted to the exact configured lookback window and locally validated by
    the same whole-word/phrase matcher used elsewhere in the project.

    A result from a tool-specific search must locally contain that same tool plus
    at least one pain term. This protects the pipeline from fuzzy or imperfect
    server-side search results. A post returned by multiple tool searches is
    emitted only once, enriched with all configured pain/tool terms it contains.
    """

    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be greater than zero")

    current_time = now_utc or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    pain_terms = list(pain_keywords)
    tool_terms = list(tools)
    cutoff_timestamp = (
        current_time.astimezone(timezone.utc) - timedelta(hours=lookback_hours)
    ).timestamp()

    all_subreddits = reddit.subreddit("all")
    matched_by_id: dict[str, dict[str, object]] = {}

    for tool in tool_terms:
        query = build_tool_search_query(pain_terms, tool)
        tool_matches = 0

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

            # First verify the exact tool used by this server-side query.
            if match_post(
                raw_post,
                pain_terms,
                [tool],
                case_sensitive=case_sensitive,
            ) is None:
                continue

            # Then enrich with every configured pain/tool term present in the post.
            matched_post = match_post(
                raw_post,
                pain_terms,
                tool_terms,
                case_sensitive=case_sensitive,
            )
            if matched_post is None:
                continue

            post_id = str(matched_post["post_id"])
            if post_id not in matched_by_id:
                matched_by_id[post_id] = matched_post
                tool_matches += 1

        LOGGER.info(
            "Global Reddit search for tool %r found %d new pain+tool matches",
            tool,
            tool_matches,
        )

    return list(matched_by_id.values())
