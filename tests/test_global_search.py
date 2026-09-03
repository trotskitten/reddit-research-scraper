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
    def __init__(self, results):
        self.results = results
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return iter(self.results)


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


def test_global_search_uses_one_boolean_query_and_locally_verifies_matches():
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
        [relevant, no_pain, old_relevant, second_relevant, duplicate_relevant]
    )
    reddit = FakeReddit(all_subreddit)

    results = search_reddit_by_keywords(
        reddit,
        ["blocked", "waiting on", "scattered"],
        ["jira", "slack"],
        6,
        now_utc=now,
    )

    assert reddit.requested == ["all"]
    assert len(all_subreddit.calls) == 1

    query, kwargs = all_subreddit.calls[0]
    assert query == (
        '("blocked" OR "waiting on" OR "scattered") '
        'AND ("jira" OR "slack")'
    )
    assert kwargs["sort"] == "new"
    assert kwargs["syntax"] == "lucene"
    assert kwargs["time_filter"] == "day"

    assert [post["post_id"] for post in results] == ["a", "c"]
    assert results[0]["matched_pain_keywords"] == ["blocked"]
    assert results[0]["matched_tools"] == ["jira"]
    assert results[1]["matched_pain_keywords"] == ["waiting on", "scattered"]
    assert results[1]["matched_tools"] == ["slack"]


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
