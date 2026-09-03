"""Diagnostic: measure refined global keyword-search coverage for a 3-hour cadence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from reddit_scraper.global_search import build_global_search_query
from reddit_scraper.matcher import match_post
from reddit_scraper.scraper import create_reddit_client, submission_to_raw_post

CONFIG_PATH = Path("config/config.yaml")
SEARCH_LIMIT = 250

# Refined from the previous diagnostics so every query should cover materially
# more than the intended 3-hour schedule interval.
QUERY_GROUPS = [
    ["blocked", "blocker", "blockers"],
    ["waiting on", "dependencies"],
    ["other team", "another team", "cross-team", "handoff", "bottleneck"],
    ["stuck", "delays"],
    ["ownership"],
    ["who owns", "no owner"],
    ["accountable"],
    ["assignee"],
    ["decisions"],
    ["decision log", "meeting notes"],
    ["rationale", "reasoning"],
    ["reconstruct"],
    ["source of truth", "stale"],
    ["status reporting", "project health", "visibility", "out of sync", "follow-up"],
    ["chasing", "action items", "scope change", "scattered", "fragmented"],
]


def dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def fmt(ts: float) -> str:
    return dt(ts).isoformat()


def hours_between(newest: float, oldest: float) -> float:
    return (newest - oldest) / 3600.0


def main() -> None:
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    all_pains = list(config["pain_keywords"])
    tools = list(config["tools"])
    case_sensitive = bool(config.get("matching", {}).get("case_sensitive", False))
    reddit = create_reddit_client()

    configured = [term for group in QUERY_GROUPS for term in group]
    if sorted(configured) != sorted(all_pains):
        raise RuntimeError("QUERY_GROUPS must contain every configured pain keyword exactly once")

    all_raw: dict[str, object] = {}
    all_exact: dict[str, dict[str, object]] = {}
    summed_raw = 0
    summed_exact = 0

    print(f"Pain keywords covered: {len(configured)}")
    print(f"Tools per query: {len(tools)}")
    print(f"Queries: {len(QUERY_GROUPS)}")
    print(f"Per-query limit: {SEARCH_LIMIT}")
    print("Local validation: at least one configured pain + at least one configured tool")

    for query_num, pain_group in enumerate(QUERY_GROUPS, start=1):
        query = build_global_search_query(pain_group, tools)
        submissions = list(
            reddit.subreddit("all").search(
                query,
                sort="new",
                syntax="lucene",
                time_filter="all",
                limit=SEARCH_LIMIT,
            )
        )

        exact: list[dict[str, object]] = []
        for submission in submissions:
            post_id = str(submission.id)
            all_raw[post_id] = submission
            raw_post = submission_to_raw_post(submission)
            matched = match_post(
                raw_post,
                all_pains,
                tools,
                case_sensitive=case_sensitive,
            )
            if matched is not None:
                exact.append(matched)
                all_exact[str(matched["post_id"])] = matched

        summed_raw += len(submissions)
        summed_exact += len(exact)

        if submissions:
            newest = max(float(item.created_utc) for item in submissions)
            oldest = min(float(item.created_utc) for item in submissions)
            raw_window_hours = hours_between(newest, oldest)
            raw_window = (
                f"raw_newest={fmt(newest)} | raw_oldest={fmt(oldest)} | "
                f"raw_window_hours={raw_window_hours:.2f}"
            )
        else:
            raw_window = "raw_newest=None | raw_oldest=None | raw_window_hours=0.00"

        if exact:
            exact_newest = max(float(item["created_utc"]) for item in exact)
            exact_oldest = min(float(item["created_utc"]) for item in exact)
            exact_window_hours = hours_between(exact_newest, exact_oldest)
            exact_window = (
                f"exact_newest={fmt(exact_newest)} | exact_oldest={fmt(exact_oldest)} | "
                f"exact_window_hours={exact_window_hours:.2f}"
            )
        else:
            exact_window = "exact_newest=None | exact_oldest=None | exact_window_hours=0.00"

        precision = (len(exact) / len(submissions) * 100.0) if submissions else 0.0
        print(
            f"QUERY {query_num:02d} | pains={pain_group} | raw={len(submissions)} | "
            f"exact={len(exact)} | exact_pct={precision:.1f}% | {raw_window} | {exact_window}"
        )

    print("\nTOTALS")
    print(f"Summed raw results across queries: {summed_raw}")
    print(f"Distinct raw posts after cross-query dedupe: {len(all_raw)}")
    print(f"Summed exact matches across queries: {summed_exact}")
    print(f"Distinct exact pain+tool matches after cross-query dedupe: {len(all_exact)}")

    if all_raw:
        newest = max(float(item.created_utc) for item in all_raw.values())
        oldest = min(float(item.created_utc) for item in all_raw.values())
        print(f"Overall raw newest: {fmt(newest)}")
        print(f"Overall raw oldest: {fmt(oldest)}")

    if all_exact:
        newest = max(float(item["created_utc"]) for item in all_exact.values())
        oldest = min(float(item["created_utc"]) for item in all_exact.values())
        print(f"Overall exact newest: {fmt(newest)}")
        print(f"Overall exact oldest: {fmt(oldest)}")


if __name__ == "__main__":
    main()
