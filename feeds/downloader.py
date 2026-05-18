import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests

from naming import entry_base

logger = logging.getLogger(__name__)

USER_AGENT = "Laeser/0.1 (polite downloader)"
TIMEOUT_SECONDS = 300
DEFAULT_DELAY_SECONDS = 5


def download_file(
    url: str,
    dest_path: Path,
    delay_seconds: int = DEFAULT_DELAY_SECONDS,
) -> bool:
    """
    Download a file to dest_path with HTTP range-request resume support.
    Returns True on success, False on failure.
    Waits delay_seconds before starting (for polite rate limiting in bulk downloads).
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for existing partial download
    headers = {"User-Agent": USER_AGENT}
    existing_size = dest_path.stat().st_size if dest_path.exists() else 0
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"
        logger.info(f"Resuming download at byte {existing_size}: {url}")

    if delay_seconds > 0:
        time.sleep(delay_seconds)

    try:
        response = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS, stream=True)

        if response.status_code == 416:
            # Range not satisfiable — file already complete
            logger.info(f"Already complete: {dest_path.name}")
            return True

        if response.status_code == 404:
            logger.warning(f"Not found (404): {url}")
            return False

        response.raise_for_status()

        mode = "ab" if existing_size > 0 and response.status_code == 206 else "wb"
        with open(dest_path, mode) as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        actual_size = dest_path.stat().st_size
        logger.info(f"Downloaded {dest_path.name} ({actual_size / 1024 / 1024:.1f} MB)")
        return True

    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        # Clean up partial file only if we started fresh (not a resume)
        if existing_size == 0 and dest_path.exists():
            dest_path.unlink()
        return False


def audio_dest_path(
    library: Path,
    folder_name: str,
    title: str,
    pub_date: Optional[str],
    url: str,
) -> Path:
    """Build the on-disk destination for an entry's audio file.

    The extension is taken from the URL's last path segment only when it is a
    short alphanumeric token; otherwise it falls back to 'mp3'. This avoids the
    garbage extensions produced by extensionless URLs.
    """
    last_segment = urlparse(url).path.rsplit("/", 1)[-1]
    ext = last_segment.rsplit(".", 1)[-1] if "." in last_segment else ""
    if not (ext and len(ext) <= 5 and ext.isalnum()):
        ext = "mp3"
    return library / folder_name / f"{entry_base(title, pub_date)}.{ext}"
