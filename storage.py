import os
import re
from datetime import datetime, timezone
from pathlib import Path

import frontmatter


def get_library_path() -> Path:
    """Return library path. Override with LAESER_LIBRARY_PATH env var for testing."""
    return Path(os.environ.get("LAESER_LIBRARY_PATH", "library"))


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug, max 80 chars."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:80]


def write_entry_file(entry: dict) -> Path:
    """
    Write or overwrite an entry as a markdown file with YAML frontmatter.
    Returns the Path of the written file.

    entry dict keys: title, source_name, source_folder, author, pub_date,
                     url, audio_path, description, tags (list of str)
    """
    library = get_library_path()
    source_folder = library / entry["source_folder"]
    source_folder.mkdir(parents=True, exist_ok=True)

    pub_date = entry.get("pub_date") or ""
    date_prefix = pub_date[:10] if pub_date else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = slugify(entry["title"])
    file_path = source_folder / f"{date_prefix}-{slug}.md"

    post = frontmatter.Post(
        entry.get("description") or "",
        title=entry["title"],
        source=entry["source_name"],
        author=entry.get("author") or "",
        pub_date=pub_date,
        url=entry.get("url") or "",
        audio_path=entry.get("audio_path") or "",
        tags=entry.get("tags") or [],
    )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(frontmatter.dumps(post))

    return file_path
