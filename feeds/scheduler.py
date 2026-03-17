import logging
import os
from pathlib import Path

# BackgroundScheduler (thread-based) is correct here: refresh_source() is sync blocking I/O.
# AsyncIOScheduler requires coroutines and would block the event loop with sync functions.
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from db.entries import create_entry, update_entry_audio_path, update_entry_fetch_status
from db.sources import list_sources, update_source_fetch_status
from feeds.downloader import download_file
from feeds.fetcher import fetch_and_parse_feed

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()
REFRESH_INTERVAL_HOURS = 6


def refresh_source(source_id: int, source: dict) -> None:
    """Fetch a source's feed and upsert entries. Downloads audio for full_archive sources."""
    logger.info(f"Refreshing source: {source['name']}")
    try:
        entries = fetch_and_parse_feed(source["feed_url"])
        update_source_fetch_status(source_id, error=None)
    except Exception as e:
        logger.error(f"Failed to fetch {source['name']}: {e}")
        update_source_fetch_status(source_id, error=str(e))
        return

    for parsed in entries:
        entry = create_entry(
            source_id=source_id,
            title=parsed["title"] or "Untitled",
            url=parsed["url"],
            author=parsed.get("author"),
            description=parsed.get("description"),
            pub_date=parsed.get("pub_date"),
            duration=parsed.get("duration"),
        )
        update_entry_fetch_status(entry["id"], "ok")

        if source["archive_mode"] == "full_archive" and parsed.get("enclosure_url"):
            _download_audio(entry, parsed["enclosure_url"], source["folder_name"])


def _download_audio(entry: dict, url: str, folder_name: str) -> None:
    """Download audio for an entry if not already present."""
    library = Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))
    ext = url.split(".")[-1].split("?")[0] or "mp3"
    filename = f"{entry['pub_date'][:10] if entry.get('pub_date') else 'unknown'}-{entry['id']}.{ext}"
    dest = library / folder_name / filename

    if dest.exists():
        return  # already downloaded

    success = download_file(url, dest, delay_seconds=3)
    if success:
        # Store path relative to library root (e.g. "security-now/sn-1047.mp3")
        # The /audio/{file_path} route appends this to the library root to serve the file.
        audio_path = str(dest.relative_to(library))
        update_entry_audio_path(entry["id"], audio_path)
        logger.info(f"Audio saved: {audio_path}")


def refresh_all() -> None:
    """Refresh all non-manual sources."""
    for source in list_sources():
        if source["type"] == "manual" or not source.get("feed_url"):
            continue
        refresh_source(source["id"], source)


def setup_scheduler(app) -> None:
    """Attach scheduler to app lifespan — start on startup, stop on shutdown."""
    _scheduler.add_job(
        refresh_all,
        trigger=IntervalTrigger(hours=REFRESH_INTERVAL_HOURS),
        id="refresh_all",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(f"Scheduler started — refreshing every {REFRESH_INTERVAL_HOURS}h")


def shutdown_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
