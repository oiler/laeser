import feedparser
from typing import Optional


def parse_feed_entry(entry) -> dict:
    """Extract a normalised dict from a feedparser entry object."""
    enclosure_url: Optional[str] = None
    for enc in getattr(entry, "enclosures", []):
        if getattr(enc, "type", "").startswith("audio/"):
            enclosure_url = getattr(enc, "href", None)
            break

    return {
        "title": getattr(entry, "title", "") or "",
        "url": getattr(entry, "link", None),
        "author": getattr(entry, "author", None),
        "description": getattr(entry, "summary", None) or getattr(entry, "description", None),
        "pub_date": getattr(entry, "published", None),
        "duration": getattr(entry, "itunes_duration", None),
        "enclosure_url": enclosure_url,
    }


def fetch_and_parse_feed(url: str) -> list[dict]:
    """
    Fetch and parse an RSS/Atom feed URL.
    Returns a list of normalised entry dicts.
    Raises ValueError if the feed is malformed (bozo).
    """
    feed = feedparser.parse(url)
    if feed.bozo:
        raise ValueError(f"Malformed feed at {url}: {feed.bozo_exception}")
    return [parse_feed_entry(e) for e in feed.entries]
