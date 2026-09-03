"""Post deduplication layer.

Deduplication order:
1. exact Reddit post id;
2. exact non-empty selftext.

No lowercasing, whitespace trimming, fuzzy matching, or other normalization is
performed. New posts are processed in source order and duplicates inside the
same new batch are removed as well as duplicates already present in storage.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping


def _post_id(post: Mapping[str, object]) -> str:
    """Return a post id as a string, or an empty string when missing."""

    value = post.get("id")
    return "" if value is None else str(value)


def _post_text(post: Mapping[str, object]) -> str:
    """Return selftext exactly as supplied, or an empty string when missing."""

    value = post.get("selftext")
    return "" if value is None else str(value)


def deduplicate_posts(
    new_posts: Iterable[Mapping[str, object]],
    existing_posts: Iterable[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Return only new posts that are not already represented in the dataset.

    The checks are deliberately ordered. A candidate is rejected first when its
    exact ``id`` has already been seen. Only surviving candidates are checked
    against exact ``selftext``.

    Empty ``selftext`` is not used as a duplicate key. Reddit link/image posts
    commonly have an empty body, so treating an empty string as content would
    incorrectly collapse unrelated posts.

    Accepted candidates are immediately added to the seen sets, which also
    removes duplicates occurring within the same scraper batch.
    """

    existing = list(existing_posts)

    seen_ids = {
        post_id
        for post in existing
        if (post_id := _post_id(post))
    }
    seen_texts = {
        text
        for post in existing
        if (text := _post_text(post))
    }

    unique_posts: list[dict[str, object]] = []

    for post in new_posts:
        post_id = _post_id(post)
        text = _post_text(post)

        if post_id and post_id in seen_ids:
            continue

        if text and text in seen_texts:
            continue

        accepted = dict(post)
        unique_posts.append(accepted)

        if post_id:
            seen_ids.add(post_id)
        if text:
            seen_texts.add(text)

    return unique_posts
