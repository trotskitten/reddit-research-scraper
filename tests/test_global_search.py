from datetime import datetime, timezone

from reddit_scraper.global_search import build_global_search_query, search_reddit_by_keywords


class FakeSubredditName:
    def __init__(self, display_name):
        self.display_name = display_name


class FakeSubmission:
    def __init__(self, post_id, title, text, created_utc, subreddit="somewhere"):
        self.id = post_id
        self.title = title
        self.selftext = text
        self.created_utc = created_utc
        self.subreddit = FakeSubredditName(subreddit)
        self.author = "author"
        self.score = 1
        self.num_comments = 0
        self.permalink = f"/r/{subreddit}/comments/{post_id}/test/"


class FakeAll:
    def __init__(self, results_by_call):
        self.results_by_call = list(results_by_call)
        self.calls = []

    def search(self, query, **kwargs):
        call_index = len(self.calls)
        self.calls.append((query, kwargs))
        if call_index >= len(self.results_by_call):
            return iter([])
        return iter(self.results_by_call[call_index])


class FakeReddit:
    def __init__(self, all_subreddit):
        self.all_subreddit = all_subreddit
        self.requested = []

    def subreddit(self, name):
        self.requested.append(name)
        assert name == "all"
        return self.all_subreddit


def test_build_global_search_query_groups_pains_and_tools():
    query = build_global_search_query(
        ["blocked", "waiting on"],
        ["jira", "slack"],
    )

    assert query == '("blocked" OR "waiting on") AND ("jira" OR "slack")'


def test_global_search_batches_queries_and_locally_verifies_full_vocab():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    now_ts = now.timestamp()

    relevant = FakeSubmission(
        "a",
        "Blocked project",
        "We track it in Jira.",
        now_ts - 60,
    )
    no_pain = FakeSubmission(
        "b",
        "Jira configuration question",
        "How do I rename a field?",
        now_ts - 120,
    )
    old_relevant = FakeSubmission(
        "old",
        "Blocked in Jira",
        "Still blocked.",
        now_ts - (7 * 3600),
    )
    second_relevant = FakeSubmission(
        "c",
        "Waiting on another team",
        "Updates are scattered across Slack.",
        now_ts - 180,
    )
    duplicate_relevant = FakeSubmission(
        "a",
        "Blocked project",
        "We track it in Jira.",
        now_ts - 60,
    )

    all_subreddit = FakeAll(
        [
            [relevant, no_pain, old_relevant, duplicate_relevant],
            [second_relevant, duplicate_relevant],
        ]
    )
    reddit = FakeReddit(all_subreddit)

    results = search_reddit_by_keywords(
        reddit,
        ["blocked", "waiting on", "scattered"],
        ["jira", "slack"],
        6,
        now_utc=now,
        batch_size=2,
    )

    assert reddit.requested == ["all"]
    assert len(all_subreddit.calls) == 2

    first_query, first_kwargs = all_subreddit.calls[0]
    second_query, second_kwargs = all_subreddit.calls[1]

    assert first_query == (
        '("blocked" OR "waiting on") '
        'AND ("jira" OR "slack")'
    )
    assert second_query == '("scattered") AND ("jira" OR "slack")'

    for kwargs in (first_kwargs, second_kwargs):
        assert kwargs["sort"] == "new"
        assert kwargs["syntax"] == "lucene"
        assert kwargs["time_filter"] == "day"
        assert kwargs["limit"] == 250

    assert [post["post_id"] for post in results] == ["a", "c"]
    assert results[0]["matched_pain_keywords"] == ["blocked"]
    assert results[0]["matched_tools"] == ["jira"]
    assert results[1]["matched_pain_keywords"] == ["waiting on", "scattered"]
    assert results[1]["matched_tools"] == ["slack"]


def test_current_35_pain_terms_produce_seven_default_queries():
    now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    pains = [f"pain-{index}" for index in range(35)]
    all_subreddit = FakeAll([[] for _ in range(7)])
    reddit = FakeReddit(all_subreddit)

    results = search_reddit_by_keywords(
        reddit,
        pains,
        ["jira"],
        6,
        now_utc=now,
    )

    assert results == []
    assert len(all_subreddit.calls) == 7
    assert all_subreddit.calls[0][0].startswith('("pain-0" OR "pain-1"')
    assert all_subreddit.calls[-1][0] == (
        '("pain-30" OR "pain-31" OR "pain-32" OR "pain-33" OR "pain-34") '
        'AND ("jira")'
    )


def test_global_search_requires_nonempty_pain_and_tool_groups():
    try:
        build_global_search_query([], ["jira"])
    except ValueError as exc:
        assert "pain" in str(exc).lower()
    else:
        raise AssertionError("Expected missing pain keywords to fail")

    try:
        build_global_search_query(["blocked"], [])
    except ValueError as exc:
        assert "tool" in str(exc).lower()
    else:
        raise AssertionError("Expected missing tools to fail")
