from datetime import datetime, timezone

from reddit_scraper.global_search import build_tool_search_query, search_reddit_by_keywords


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
    def __init__(self, jira_results, slack_results):
        self.jira_results = jira_results
        self.slack_results = slack_results
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        if '"jira"' in query:
            return iter(self.jira_results)
        if '"slack"' in query:
            return iter(self.slack_results)
        return iter([])


class FakeReddit:
    def __init__(self, all_subreddit):
        self.all_subreddit = all_subreddit
        self.requested = []

    def subreddit(self, name):
        self.requested.append(name)
        assert name == "all"
        return self.all_subreddit


def test_build_tool_search_query_combines_any_pain_with_one_tool():
    query = build_tool_search_query(["blocked", "waiting on"], "jira")

    assert query == '("blocked" OR "waiting on") AND "jira"'


def test_global_search_uses_one_search_per_tool_and_locally_verifies_matches():
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

    all_subreddit = FakeAll(
        jira_results=[relevant, no_pain, old_relevant],
        slack_results=[relevant, second_relevant],
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
    assert len(all_subreddit.calls) == 2
    assert all(call[1]["sort"] == "new" for call in all_subreddit.calls)
    assert all(call[1]["syntax"] == "lucene" for call in all_subreddit.calls)
    assert all(call[1]["time_filter"] == "day" for call in all_subreddit.calls)
    assert [post["post_id"] for post in results] == ["a", "c"]
    assert results[0]["matched_pain_keywords"] == ["blocked"]
    assert results[0]["matched_tools"] == ["jira"]
    assert results[1]["matched_pain_keywords"] == ["waiting on", "scattered"]
    assert results[1]["matched_tools"] == ["slack"]
