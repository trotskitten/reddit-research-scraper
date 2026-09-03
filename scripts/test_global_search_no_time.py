"""Diagnostic: run the full global pain+tool Reddit search with no age cutoff."""

from datetime import datetime, timezone
from pathlib import Path

import yaml

from reddit_scraper.global_search import build_global_search_query
from reddit_scraper.matcher import match_post
from reddit_scraper.scraper import create_reddit_client, submission_to_raw_post

CONFIG_PATH = Path("config/config.yaml")
SEARCH_LIMIT = 250


def main() -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    pain_keywords = config["pain_keywords"]
    tools = config["tools"]
    case_sensitive = bool(config.get("matching", {}).get("case_sensitive", False))

    query = build_global_search_query(pain_keywords, tools)
    reddit = create_reddit_client()

    submissions = list(
        reddit.subreddit("all").search(
            query,
            sort="new",
            syntax="lucene",
            time_filter="all",
            limit=SEARCH_LIMIT,
        )
    )

    matched = []
    for submission in submissions:
        raw_post = submission_to_raw_post(submission)
        match = match_post(
            raw_post,
            pain_keywords,
            tools,
            case_sensitive=case_sensitive,
        )
        if match is not None:
            matched.append(match)

    print(f"Requested search limit: {SEARCH_LIMIT}")
    print(f"Raw Reddit search results: {len(submissions)}")
    print(f"Exact local pain+tool matches: {len(matched)}")

    if submissions:
        newest = datetime.fromtimestamp(float(submissions[0].created_utc), tz=timezone.utc)
        oldest = datetime.fromtimestamp(float(submissions[-1].created_utc), tz=timezone.utc)
        print(f"Newest raw result: {newest.isoformat()}")
        print(f"Oldest raw result: {oldest.isoformat()}")

    print("\nFirst exact matches:")
    for post in matched[:20]:
        created = datetime.fromtimestamp(float(post["created_utc"]), tz=timezone.utc)
        print(
            f"MATCH | r/{post['subreddit']} | id={post['post_id']} | "
            f"created={created.isoformat()} | pain={post['matched_pain_keywords']} | "
            f"tools={post['matched_tools']} | title={post['title']}"
        )


if __name__ == "__main__":
    main()
