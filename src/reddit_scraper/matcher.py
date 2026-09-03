"""Pain-keyword and tool matching layer."""

from __future__ import annotations

import re
from collections.abc import Iterable


def build_search_text(post: dict[str, object]) -> str:
    """Combine title and body into the searchable text for one Reddit post."""

    title = str(post.get("title") or "")
    body = str(post.get("text") or "")
    return f"{title}\n{body}"


def term_matches(text: str, term: str, case_sensitive: bool = False) -> bool:
    """Return whether a whole word or phrase appears in text.

    The matcher avoids loose substring matches. For example, ``blocked`` matches
    ``blocked by another team`` but not ``unblocked``.
    """

    if not term:
        return False

    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
    return re.search(pattern, text, flags=flags) is not None


def find_matches(
    text: str,
    terms: Iterable[str],
    case_sensitive: bool = False,
) -> list[str]:
    """Return configured terms that appear in text, preserving config order."""

    return [term for term in terms if term_matches(text, term, case_sensitive)]


def match_post(
    post: dict[str, object],
    pain_keywords: Iterable[str],
    tools: Iterable[str],
    case_sensitive: bool = False,
) -> dict[str, object] | None:
    """Match one post against the WorkEnablr retrieval rule.

    A post qualifies only when the combined title + body contains at least one
    configured pain keyword/phrase AND at least one configured tool term.

    Qualifying posts are returned as a copy enriched with the exact configured
    terms that matched. Non-qualifying posts return ``None``.
    """

    search_text = build_search_text(post)
    matched_pain_keywords = find_matches(search_text, pain_keywords, case_sensitive)
    matched_tools = find_matches(search_text, tools, case_sensitive)

    if not matched_pain_keywords or not matched_tools:
        return None

    matched_post = dict(post)
    matched_post["matched_pain_keywords"] = matched_pain_keywords
    matched_post["matched_tools"] = matched_tools
    return matched_post


def filter_matching_posts(
    posts: Iterable[dict[str, object]],
    pain_keywords: Iterable[str],
    tools: Iterable[str],
    case_sensitive: bool = False,
) -> list[dict[str, object]]:
    """Return only posts satisfying the pain-keyword AND tool rule."""

    matched_posts: list[dict[str, object]] = []

    for post in posts:
        matched = match_post(post, pain_keywords, tools, case_sensitive)
        if matched is not None:
            matched_posts.append(matched)

    return matched_posts
