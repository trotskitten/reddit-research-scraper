"""Reddit retrieval layer.

This module is responsible only for:
- creating a read-only PRAW client;
- retrieving recent submissions from configured subreddits;
- returning raw Reddit post data.

Matching, cleaning, deduplication, and storage belong to other modules.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

import praw
from dotenv import load_dotenv
from prawcore.exceptions import Forbidden, NotFound, Redirect

LOGGER = logging.getLogger(__name__)
REDDIT_BASE_URL = "https://www.reddit.com"


def create_reddit_client() -> praw.Reddit:
    """Create a read-only Reddit client from environment variables.

    Local development may supply the variables through a repository-root
    ``.env`` file. GitHub Actions will inject the same names from repository
    secrets, so the application code stays identical in both environments.

    Required environment variables:
    - REDDIT_CLIENT_ID
    - REDDIT_CLIENT_SECRET
    - REDDIT_USER_AGENT
    """

    load_dotenv()

    env_names = (
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
    )
    missing = [name for name in env_names if not os.getenv(name)]

    if missing:
        missing_text = ", ".join(missing)
        raise RuntimeError(f"Missing required Reddit environment variables: {missing_text}")

    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )
    reddit.read_only = True
    return reddit


def submission_to_raw_post(submission: praw.models.Submission) -> dict[str, object]:
    """Convert a PRAW Submission into the raw post structure used downstream."""

    return {
        "post_id": submission.id,
        "subreddit": submission.subreddit.display_name,
        "title": submission.title or "",
        "text": submission.selftext or "",
        "author": str(submission.author) if submission.author else None,
        "created_utc": float(submission.created_utc),
        "score": int(submission.score),
        "num_comments": int(submission.num_comments),
        "url": f"{REDDIT_BASE_URL}{submission.permalink}",
    }


def scrape_subreddit(
    reddit: praw.Reddit,
    subreddit_name: str,
    cutoff_utc: datetime,
) -> list[dict[str, object]]:
    """Retrieve submissions from one subreddit that are newer than cutoff_utc.

    The subreddit ``new`` listing is traversed newest-first. An old sticky is
    skipped rather than used as a stopping condition because stickied posts can
    appear ahead of genuinely recent submissions.
    """

    cutoff_timestamp = cutoff_utc.timestamp()
    posts: list[dict[str, object]] = []
    subreddit = reddit.subreddit(subreddit_name)

    for submission in subreddit.new(limit=None):
        created_utc = float(submission.created_utc)

        if created_utc < cutoff_timestamp:
            if submission.stickied:
                continue
            break

        posts.append(submission_to_raw_post(submission))

    return posts


def scrape_posts(
    reddit: praw.Reddit,
    subreddits: Iterable[str],
    lookback_hours: int,
    now_utc: datetime | None = None,
) -> list[dict[str, object]]:
    """Retrieve recent raw posts from every configured subreddit.

    A subreddit that is missing, private, or redirects is logged and skipped so
    one unavailable community does not discard an otherwise valid scraper run.
    Other API/network errors are intentionally allowed to propagate so the
    pipeline can fail visibly instead of silently producing incomplete data.
    """

    if lookback_hours <= 0:
        raise ValueError("lookback_hours must be greater than zero")

    current_time = now_utc or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    cutoff_utc = current_time.astimezone(timezone.utc) - timedelta(hours=lookback_hours)
    posts: list[dict[str, object]] = []

    for subreddit_name in subreddits:
        try:
            subreddit_posts = scrape_subreddit(reddit, subreddit_name, cutoff_utc)
        except (Forbidden, NotFound, Redirect) as exc:
            LOGGER.warning("Skipping r/%s: %s", subreddit_name, exc)
            continue

        LOGGER.info(
            "Retrieved %d posts from r/%s within the last %d hours",
            len(subreddit_posts),
            subreddit_name,
            lookback_hours,
        )
        posts.extend(subreddit_posts)

    return posts
