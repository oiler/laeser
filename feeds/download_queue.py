import logging
import os
import queue
import threading
from pathlib import Path
from typing import Optional

from db.entries import (
    get_entry,
    list_entries_by_audio_status,
    set_audio_status,
    update_entry_audio_path,
)
from feeds.downloader import audio_dest_path, download_file as _download_file

logger = logging.getLogger(__name__)

# Module-level queue of entry IDs; None is the worker-stop sentinel.
_queue: "queue.Queue" = queue.Queue()
_worker: Optional[threading.Thread] = None

# Module-level reference to download_file for monkeypatching in tests
download_file = _download_file


def enqueue(entry_id: int) -> None:
    """Mark an entry queued and put it on the download queue."""
    set_audio_status(entry_id, "queued")
    _queue.put(entry_id)


def process_download(entry_id: int) -> None:
    """Download one entry's audio. No-ops on a missing entry, an entry with no
    enclosure URL, or an entry whose audio is already on disk."""
    entry = get_entry(entry_id)
    if not entry or not entry.get("enclosure_url") or entry.get("audio_path"):
        return
    set_audio_status(entry_id, "downloading")
    library = Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))
    dest = audio_dest_path(
        library, entry["source_folder"], entry["title"],
        entry.get("pub_date"), entry["enclosure_url"],
    )
    if download_file(entry["enclosure_url"], dest):
        update_entry_audio_path(entry_id, str(dest.relative_to(library)))
        set_audio_status(entry_id, "downloaded")
    else:
        set_audio_status(entry_id, "failed")


def _worker_loop() -> None:
    while True:
        entry_id = _queue.get()
        if entry_id is None:  # stop sentinel
            _queue.task_done()
            return
        try:
            process_download(entry_id)
        except Exception:
            logger.exception(f"Download failed for entry {entry_id}")
            try:
                set_audio_status(entry_id, "failed")
            except Exception:
                logger.exception(f"Could not mark entry {entry_id} as failed")
        finally:
            _queue.task_done()


def _requeue_pending() -> None:
    """Re-enqueue entries left mid-flight by a previous run."""
    for entry in list_entries_by_audio_status(["queued", "downloading"]):
        _queue.put(entry["id"])


def start_worker() -> None:
    """Start the download worker, re-enqueuing any interrupted entries first."""
    global _worker
    if _worker and _worker.is_alive():
        return
    _requeue_pending()
    _worker = threading.Thread(target=_worker_loop, daemon=True, name="download-worker")
    _worker.start()
    logger.info("Download worker started")


def stop_worker() -> None:
    """Signal the worker to exit and wait briefly for it."""
    global _worker
    if _worker and _worker.is_alive():
        _queue.put(None)
        _worker.join(timeout=5)
        if _worker.is_alive():
            # Still draining a download — leave the reference so a later
            # start_worker() sees it alive and does not spawn a duplicate.
            logger.warning("Download worker did not stop within timeout")
            return
    _worker = None
