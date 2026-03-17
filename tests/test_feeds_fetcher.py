import pytest
from unittest.mock import patch, MagicMock
from feeds.fetcher import fetch_and_parse_feed, parse_feed_entry


# Minimal feedparser-like result structure
def _fake_feed(entries):
    feed = MagicMock()
    feed.bozo = False
    feed.entries = entries
    return feed


def _fake_entry(
    title="Episode 1",
    link="https://example.com/ep1",
    summary="Show notes here",
    author="Steve Gibson",
    published="Tue, 02 Apr 2024 00:00:00 +0000",
    enclosures=None,
    itunes_duration=None,
):
    e = MagicMock()
    e.get = lambda key, default=None: {
        "title": title,
        "link": link,
        "summary": summary,
        "author": author,
        "published": published,
        "itunes_duration": itunes_duration,
    }.get(key, default)
    e.title = title
    e.link = link
    e.get("summary", "")
    e.summary = summary
    e.author = author
    e.published = published
    e.enclosures = enclosures or []
    e.itunes_duration = itunes_duration
    return e


def test_parse_feed_entry_extracts_fields():
    entry = _fake_entry()
    result = parse_feed_entry(entry)
    assert result["title"] == "Episode 1"
    assert result["url"] == "https://example.com/ep1"
    assert result["description"] == "Show notes here"
    assert result["author"] == "Steve Gibson"


def test_parse_feed_entry_extracts_audio_enclosure():
    enc = MagicMock()
    enc.type = "audio/mpeg"
    enc.href = "https://example.com/ep1.mp3"
    entry = _fake_entry(enclosures=[enc])
    result = parse_feed_entry(entry)
    assert result["enclosure_url"] == "https://example.com/ep1.mp3"


def test_parse_feed_entry_no_enclosure():
    entry = _fake_entry(enclosures=[])
    result = parse_feed_entry(entry)
    assert result["enclosure_url"] is None


def test_parse_feed_entry_extracts_duration():
    entry = _fake_entry(itunes_duration="01:23:45")
    result = parse_feed_entry(entry)
    assert result["duration"] == "01:23:45"


def test_fetch_and_parse_feed_returns_list(monkeypatch):
    fake = _fake_feed([_fake_entry(title="Ep 1", link="https://example.com/1"),
                       _fake_entry(title="Ep 2", link="https://example.com/2")])
    monkeypatch.setattr("feeds.fetcher.feedparser.parse", lambda url: fake)
    results = fetch_and_parse_feed("https://example.com/feed.rss")
    assert len(results) == 2
    assert results[0]["title"] == "Ep 1"


def test_fetch_and_parse_feed_raises_on_bozo(monkeypatch):
    fake = MagicMock()
    fake.bozo = True
    fake.bozo_exception = Exception("malformed XML")
    monkeypatch.setattr("feeds.fetcher.feedparser.parse", lambda url: fake)
    with pytest.raises(ValueError, match="malformed"):
        fetch_and_parse_feed("https://example.com/bad.rss")
