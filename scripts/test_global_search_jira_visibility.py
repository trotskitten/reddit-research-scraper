"""Live diagnostic for the global Reddit search path.

Tests exactly: "visibility" AND "jira" across r/all.
No Google Drive access and no writes.
"""

from datetime import datetime, timedelta, timezone

from reddit_scraper.global_search import build_global_search_query
from reddit_scraper.matcher import match_post
from reddit_scraper.scraper import create_reddit_client, submission_to_raw_post


def main() -> None:
    reddit = create_reddit_client()
    pain_terms = ["visibility"]
    tool_terms = ["jira"]
    query = build_global_search_query(pain_terms, tool_terms)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=6)

    print(f"Query: {query}")

    raw_count = 0
    recent_count = 0
    local_match_count = 0

    for submission in reddit.subreddit("all").search(
        query,
        sort="new",
        syntax="lucene",
        time_filter="day",
        limit=100,
    ):
        raw_count += 1
        created = datetime.fromtimestamp(float(submission.created_utc), tz=timezone.utc)
        if created < cutoff:
            continue

        recent_count += 1
        raw_post = submission_to_raw_post(submission)
        matched = match_post(raw_post, pain_terms, tool_terms)
        if matched is not None:
            local_match_count += 1
            print(
                "MATCH | "
                f"r/{raw_post['subreddit']} | "
                f"id={raw_post['post_id']} | "
                f"created={created.isoformat()} | "
                f"title={raw_post['title']}"
            )
        else:
            print(
                "REJECTED LOCALLY | "
                f"r/{raw_post['subreddit']} | "
                f"id={raw_post['post_id']} | "
                f"created={created.isoformat()} | "
                f"title={raw_post['title']}"
            )

    print(
        "Summary: "
        f"raw_search_results={raw_count}, "
        f"within_6h={recent_count}, "
        f"local_matches={local_match_count}"
    )


if __name__ == "__main__":
    main()
