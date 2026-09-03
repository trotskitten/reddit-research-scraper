"""Manual Reddit API connection test.

This script verifies that the configured Reddit credentials can authenticate
through PRAW and read at least one public submission.
"""

from reddit_scraper.scraper import create_reddit_client


def main() -> None:
    reddit = create_reddit_client()
    subreddit = reddit.subreddit("projectmanagement")
    submission = next(subreddit.new(limit=1), None)

    if submission is None:
        raise RuntimeError("Reddit connection succeeded, but no test submission was returned.")

    print("Reddit connection OK")
    print(f"Read-only mode: {reddit.read_only}")
    print(f"Test subreddit: r/{subreddit.display_name}")
    print(f"Latest post id: {submission.id}")
    print(f"Latest post title: {submission.title}")


if __name__ == "__main__":
    main()
