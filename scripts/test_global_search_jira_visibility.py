"""Live diagnostic for Reddit search: visibility AND jira.

Requests up to 250 newest search results with no age cutoff, then checks the
current title + body for the literal words "visibility" and "jira" using the
same whole-word matcher semantics as the pipeline. No Google Drive access.
"""

from datetime import datetime, timezone

from reddit_scraper.global_search import build_global_search_query
from reddit_scraper.matcher import term_matches
from reddit_scraper.scraper import create_reddit_client, submission_to_raw_post

SEARCH_LIMIT = 250


def main() -> None:
    reddit = create_reddit_client()
    query = build_global_search_query(["visibility"], ["jira"])

    print(f"Query: {query}")
    print(f"Requested limit: {SEARCH_LIMIT}")

    submissions = list(
        reddit.subreddit("all").search(
            query,
            sort="new",
            syntax="lucene",
            time_filter="all",
            limit=SEARCH_LIMIT,
        )
    )

    both = []
    only_jira = []
    only_visibility = []
    neither = []

    for submission in submissions:
        post = submission_to_raw_post(submission)
        search_text = f"{post['title']}\n{post['text']}"
        has_jira = term_matches(search_text, "jira")
        has_visibility = term_matches(search_text, "visibility")

        if has_jira and has_visibility:
            both.append(post)
        elif has_jira:
            only_jira.append(post)
        elif has_visibility:
            only_visibility.append(post)
        else:
            neither.append(post)

    print(f"Raw Reddit search results: {len(submissions)}")
    print(f"Contains BOTH jira + visibility: {len(both)}")
    print(f"Contains jira only: {len(only_jira)}")
    print(f"Contains visibility only: {len(only_visibility)}")
    print(f"Contains neither: {len(neither)}")

    if submissions:
        newest = datetime.fromtimestamp(float(submissions[0].created_utc), tz=timezone.utc)
        oldest = datetime.fromtimestamp(float(submissions[-1].created_utc), tz=timezone.utc)
        print(f"Newest returned result: {newest.isoformat()}")
        print(f"Oldest returned result: {oldest.isoformat()}")

    print("\nPosts that actually contain both words:")
    for post in both:
        created = datetime.fromtimestamp(float(post["created_utc"]), tz=timezone.utc)
        print(
            f"BOTH | r/{post['subreddit']} | id={post['post_id']} | "
            f"created={created.isoformat()} | title={post['title']}"
        )


if __name__ == "__main__":
    main()
