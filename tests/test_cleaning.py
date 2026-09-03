from reddit_scraper.cleaning import DATASET_COLUMNS, clean_post, clean_posts


def test_clean_post_matches_existing_dataset_schema():
    post = {
        "post_id": "abc123",
        "subreddit": "projectmanagement",
        "title": "Blocked by another team",
        "text": "We are waiting on Jira updates. ",
        "author": "example_user",
        "created_utc": 1787681430.0,
        "url": "https://www.reddit.com/r/projectmanagement/comments/abc123/example/",
        "matched_pain_keywords": ["blocked", "waiting on"],
        "matched_tools": ["jira"],
    }

    cleaned = clean_post(post)

    assert tuple(cleaned.keys()) == DATASET_COLUMNS
    assert cleaned == {
        "subreddit": "projectmanagement",
        "id": "abc123",
        "title": "Blocked by another team",
        "author": "example_user",
        "created_utc": 1787681430.0,
        "created_iso": "2026-08-25T18:10:30+00:00",
        "url": "https://www.reddit.com/r/projectmanagement/comments/abc123/example/",
        "selftext": "We are waiting on Jira updates. ",
    }


def test_clean_post_preserves_body_text_exactly():
    body = "  First line\n\nSecond line with trailing space. "
    post = {
        "post_id": "abc123",
        "subreddit": "jira",
        "title": "Example",
        "text": body,
        "author": None,
        "created_utc": 1787681430,
        "url": "https://www.reddit.com/example",
    }

    cleaned = clean_post(post)

    assert cleaned["selftext"] == body
    assert cleaned["author"] == ""


def test_clean_posts_keeps_order():
    posts = [
        {
            "post_id": "one",
            "subreddit": "jira",
            "title": "One",
            "text": "Body one",
            "author": "a",
            "created_utc": 1787681430,
            "url": "https://www.reddit.com/one",
        },
        {
            "post_id": "two",
            "subreddit": "Slack",
            "title": "Two",
            "text": "Body two",
            "author": "b",
            "created_utc": 1787681431,
            "url": "https://www.reddit.com/two",
        },
    ]

    cleaned = clean_posts(posts)

    assert [row["id"] for row in cleaned] == ["one", "two"]


def test_clean_post_requires_id_and_timestamp():
    base = {
        "subreddit": "jira",
        "title": "Example",
        "text": "Body",
        "author": "a",
        "url": "https://www.reddit.com/example",
    }

    try:
        clean_post({**base, "created_utc": 1787681430})
    except ValueError as exc:
        assert str(exc) == "post_id is required"
    else:
        raise AssertionError("Expected missing post_id to raise ValueError")

    try:
        clean_post({**base, "post_id": "abc123"})
    except ValueError as exc:
        assert str(exc) == "created_utc is required"
    else:
        raise AssertionError("Expected missing created_utc to raise ValueError")
