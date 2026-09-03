# Reddit Research Scraper

Automated Reddit scraper for WorkEnablr research.

The pipeline has two independent Reddit retrieval streams:

1. **Curated subreddit scrape** — collect every post from the configured 30 subreddits inside the lookback window. No keyword match is required.
2. **Global Reddit search** — search r/all for posts containing at least one configured pain term and at least one configured tool term.

The streams are then merged, cleaned to the canonical dataset schema, deduplicated, and appended to the Google Drive dataset.

Pipeline:

`30 subreddits (all recent posts) + global pain/tool search -> cleaning -> deduplication -> Google Drive dataset`

The production workflow is intended to run via GitHub Actions every 3 hours with a 6-hour overlapping lookback.

## Architecture

- `config/config.yaml` — editable subreddits, pain terms, tools, and scraper configuration
- `src/reddit_scraper/scraper.py` — unfiltered curated-subreddit retrieval
- `src/reddit_scraper/global_search.py` — pain + tool search across r/all
- `src/reddit_scraper/matcher.py` — local whole-word/phrase verification for global search results
- `src/reddit_scraper/cleaning.py` — canonical dataset schema cleaning
- `src/reddit_scraper/deduplication.py` — exact ID then exact non-empty body duplicate removal
- `src/reddit_scraper/drive_storage.py` — Google Drive dataset I/O
- `src/reddit_scraper/pipeline.py` — pipeline orchestration
- `tests/` — unit tests
- `.github/workflows/` — GitHub Actions workflows
