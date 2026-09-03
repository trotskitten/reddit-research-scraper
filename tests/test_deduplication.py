from reddit_scraper.deduplication import deduplicate_posts


def test_removes_existing_post_id_before_text_check():
    existing = [{"id": "abc", "selftext": "original body"}]
    new = [{"id": "abc", "selftext": "different body"}]

    assert deduplicate_posts(new, existing) == []


def test_removes_exact_existing_selftext_with_different_id():
    existing = [{"id": "abc", "selftext": "same body"}]
    new = [{"id": "xyz", "selftext": "same body"}]

    assert deduplicate_posts(new, existing) == []


def test_exact_text_comparison_does_not_normalize_case_or_whitespace():
    existing = [{"id": "abc", "selftext": "Same body"}]
    new = [
        {"id": "one", "selftext": "same body"},
        {"id": "two", "selftext": "Same body "},
    ]

    assert deduplicate_posts(new, existing) == new


def test_removes_duplicate_ids_inside_same_new_batch():
    new = [
        {"id": "abc", "selftext": "first body"},
        {"id": "abc", "selftext": "second body"},
    ]

    assert deduplicate_posts(new, []) == [new[0]]


def test_removes_duplicate_text_inside_same_new_batch():
    new = [
        {"id": "abc", "selftext": "same body"},
        {"id": "xyz", "selftext": "same body"},
    ]

    assert deduplicate_posts(new, []) == [new[0]]


def test_empty_selftext_is_not_treated_as_duplicate_content():
    existing = [{"id": "abc", "selftext": ""}]
    new = [
        {"id": "one", "selftext": ""},
        {"id": "two", "selftext": ""},
    ]

    assert deduplicate_posts(new, existing) == new


def test_preserves_source_order_for_surviving_posts():
    existing = [{"id": "old", "selftext": "old body"}]
    new = [
        {"id": "one", "selftext": "body one"},
        {"id": "old", "selftext": "new body"},
        {"id": "two", "selftext": "body two"},
    ]

    assert deduplicate_posts(new, existing) == [new[0], new[2]]
