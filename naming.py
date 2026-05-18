import re
from datetime import datetime, timezone
from typing import Optional


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug, max 80 chars."""
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")[:80]


def date_prefix(pub_date: Optional[str]) -> str:
    """
    Return a YYYY-MM-DD prefix from a pub_date string.
    Falls back to today's UTC date if pub_date is missing or empty.
    """
    if pub_date:
        return pub_date[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def entry_base(title: str, pub_date: Optional[str]) -> str:
    """
    Return the shared base name '<YYYY-MM-DD>-<slug>' used for both the
    markdown file and the audio file of an entry.
    """
    return f"{date_prefix(pub_date)}-{slugify(title)}"
