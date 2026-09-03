"""Diagnostic: measure recency coverage of batched global pain+tool searches."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from reddit_scraper.global_search import build_global_search_query
from reddit_scraper.matcher import match_post
from reddit_scraper.scraper import create_reddit_client, submission_to_raw_post

CONFIG_PATH = Path("config/config.yaml")
BATCH_SIZE = 5
SEARCH_LIMIT = 250


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def main() -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    pain_keywords = list(config["pain_keywords"])
    tools = list(config["tools"])
    case_sensitive = bool(config.get("matching", {}).get("case_sensitive", False))
    reddit = create_reddit_client()

    all_raw: dict[str, object] = {}
    all_exact: dict[str, dict[str, object]] = {}

    print(f"Pain keywords: {len(pain_keywords)}")
    print(f"Tools: {len(tools)}")
    print(f"Batch size: {BATCH_SIZE}")
    print(f"Per-query limit: {SEARCH_LIMIT}")

    for index in range(0, len(pain_keywords), BATCH_SIZE):
        pain_batch = pain_keywords[index:index + BATCH_SIZE]
        query = build_global_search_query(pain_batch, tools)
        submissions = list(
            reddit.subreddit("all").search(
                query,
                sort="new",
                syntax="lucene",
                time_filter="all",
                limit=SEARCH_LIMIT,
            )
        )

        exact = []
        for submission in submissions:
            all_raw[str(submission.id)] = submission
            raw_post = submission_to_raw_post(submission)
            matched = match_post(
                raw_post,
                pain_batch,
                tools,
                case_sensitive=case_sensitive,
            )
            if matched is not None:
                exact.append(matched)
                all_exact[str(matched["post_id"])] = matched

        batch_num = index // BATCH_SIZE + 1
        if submissions:
            newest = max(float(item.created_utc) for item in submissions)
            oldest = min(float(item.created_utc) for item in submissions)
            raw_window = f"newest={iso(newest)} | oldest={iso(oldest)}"
        else:
            raw_window = "newest=None | oldest=None"

        if exact:
            exact_newest = max(float(item["created_utc"]) for item in exact)
            exact_oldest = min(float(item["created_utc"]) for item in exact)
            exact_window = f"exact_newest={iso(exact_newest)} | exact_oldest={iso(exact_oldest)}"
        else:
            exact_window = "exact_newest=None | exact_oldest=None"

        print(
            f"BATCH {batch_num} | pains={pain_batch} | raw={len(submissions)} | "
            f"exact={len(exact)} | {raw_window} | {exact_window}"
        )

    print("\nOVERALL DISTINCT RESULTS")
    print(f"Raw distinct posts: {len(all_raw)}")
    print(f"Exact distinct pain+tool matches: {len(all_exact)}")

    if all_raw:
        newest = max(float(item.created_utc) for item in all_raw.values())
        oldest = min(float(item.created_utc) for item in all_raw.values())
        print(f"Overall raw newest: {iso(newest)}")
        print(f"Overall raw oldest: {iso(oldest)}")

    if all_exact:
        exact_newest = max(float(item["created_utc"]) for item in all_exact.values())
        exact_oldest = min(float(item["created_utc"]) for item in all_exact.values())
        print(f"Overall exact newest: {iso(exact_newest)}")
        print(f"Overall exact oldest: {iso(exact_oldest)}")


if __name__ == "__main__":
    main()
