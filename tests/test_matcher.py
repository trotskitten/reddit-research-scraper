from reddit_scraper.matcher import filter_matching_posts, match_post, term_matches


PAIN = ["blocked", "waiting on", "source of truth", "who owns"]
TOOLS = ["jira", "slack", "notion", "github"]


def test_matches_when_pain_and_tool_are_split_between_title_and_body():
    post = {
        "title": "Blocked waiting on another team",
        "text": "We track the work in Jira.",
    }

    matched = match_post(post, PAIN, TOOLS)

    assert matched is not None
    assert "blocked" in matched["matched_pain_keywords"]
    assert "waiting on" in matched["matched_pain_keywords"]
    assert matched["matched_tools"] == ["jira"]


def test_does_not_match_without_tool():
    post = {
        "title": "Blocked waiting on another team",
        "text": "No tooling mentioned here.",
    }

    assert match_post(post, PAIN, TOOLS) is None


def test_does_not_match_without_pain_keyword():
    post = {
        "title": "Our Jira setup",
        "text": "Everything is working normally.",
    }

    assert match_post(post, PAIN, TOOLS) is None


def test_matching_is_case_insensitive():
    post = {
        "title": "BLOCKED",
        "text": "This work is tracked in JIRA.",
    }

    matched = match_post(post, PAIN, TOOLS)

    assert matched is not None
    assert matched["matched_pain_keywords"] == ["blocked"]
    assert matched["matched_tools"] == ["jira"]


def test_word_matching_does_not_match_unblocked_for_blocked():
    assert not term_matches("The task is now unblocked in Jira", "blocked")


def test_phrase_matching_uses_phrase_boundaries():
    assert term_matches("We need one source of truth in Notion", "source of truth")


def test_filter_matching_posts_keeps_only_qualifying_posts():
    posts = [
        {"post_id": "1", "title": "Who owns this?", "text": "It is in Slack."},
        {"post_id": "2", "title": "Jira question", "text": "How do I change a field?"},
        {"post_id": "3", "title": "Blocked again", "text": "Still waiting."},
    ]

    matched = filter_matching_posts(posts, PAIN, TOOLS)

    assert [post["post_id"] for post in matched] == ["1"]
