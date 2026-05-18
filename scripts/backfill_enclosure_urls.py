"""
One-shot backfill: populate entries.enclosure_url for existing entries by
re-fetching each source's feed and matching items on guid/url.

Does not download audio and does not create entries — it only fills in
enclosure URLs that are currently null.

Usage:
    uv run python -m scripts.backfill_enclosure_urls           # apply
    uv run python -m scripts.backfill_enclosure_urls --dry-run # preview
"""
import argparse
import logging
from typing import Optional

from db.connection import get_db
from db.entries import set_enclosure_url
from db.sources import list_sources
from feeds.fetcher import fetch_and_parse_feed

logger = logging.getLogger("backfill_enclosure_urls")


def _find_entry(guid: Optional[str], url: Optional[str]) -> Optional[dict]:
    """Find an existing entry by guid, falling back to url."""
    with get_db() as conn:
        if guid:
            row = conn.execute(
                "SELECT id, enclosure_url FROM entries WHERE guid = ?", (guid,)
            ).fetchone()
            if row:
                return dict(row)
        if url:
            row = conn.execute(
                "SELECT id, enclosure_url FROM entries WHERE url = ?", (url,)
            ).fetchone()
            if row:
                return dict(row)
    return None


def backfill(dry_run: bool = False) -> None:
    for source in list_sources():
        if source["type"] == "manual" or not source.get("feed_url"):
            continue
        try:
            items = fetch_and_parse_feed(source["feed_url"])
        except Exception as exc:
            logger.error(f"{source['name']}: feed fetch failed: {exc}")
            continue

        updated = skipped = 0
        for item in items:
            if not item.get("enclosure_url"):
                continue
            entry = _find_entry(item.get("guid"), item.get("url"))
            if not entry or entry["enclosure_url"]:
                skipped += 1
                continue
            if dry_run:
                logger.info(f"DRY-RUN set enclosure_url for entry {entry['id']}")
            else:
                set_enclosure_url(entry["id"], item["enclosure_url"])
            updated += 1
        logger.info(f"{source['name']}: updated {updated}, skipped {skipped}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned updates without touching the DB.",
    )
    args = parser.parse_args()
    backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
