# Reddit Research Scraper

Automated Reddit scraper for WorkEnablr research.

Pipeline:

`Reddit -> matching -> cleaning -> deduplication -> Google Drive dataset`

The scraper will run via GitHub Actions every 3 hours.

## Architecture

- `config/config.yaml` — editable scraper configuration
- `src/reddit_scraper/scraper.py` — Reddit retrieval
- `src/reddit_scraper/matcher.py` — keyword/tool matching
- `src/reddit_scraper/cleaning.py` — schema cleaning
- `src/reddit_scraper/deduplication.py` — duplicate removal
- `src/reddit_scraper/drive_storage.py` — Google Drive dataset I/O
- `src/reddit_scraper/pipeline.py` — pipeline orchestration
- `tests/` — unit tests
- `.github/workflows/` — scheduled GitHub Actions workflow
