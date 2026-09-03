"""Read-only Google Drive dataset connection test.

This script authenticates with the configured service account, downloads the
canonical dataset, validates its schema, and prints basic metadata. It never
uploads or modifies Drive content.
"""

from reddit_scraper.drive_storage import (
    DATASET_COLUMNS,
    create_drive_service,
    download_dataset,
    get_dataset_file_id,
)


def main() -> None:
    service = create_drive_service()
    file_id = get_dataset_file_id()
    snapshot = download_dataset(service, file_id)

    print("Google Drive connection OK")
    print(f"Dataset file id: {file_id}")
    print(f"Dataset rows: {len(snapshot.rows)}")
    print(f"Dataset columns: {', '.join(DATASET_COLUMNS)}")
    print(f"Downloaded bytes: {len(snapshot.raw_bytes)}")


if __name__ == "__main__":
    main()
