"""Run the real Reddit pipeline with Drive writes disabled."""

import logging

from reddit_scraper.pipeline import run_pipeline


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    result = run_pipeline(dry_run=True)
    print(
        "Dry run complete: "
        f"existing={result.existing_rows}, "
        f"scraped={result.scraped_posts}, "
        f"matched={result.matched_posts}, "
        f"unique={result.unique_posts}, "
        f"uploaded={result.uploaded}"
    )


if __name__ == "__main__":
    main()
