import pytest

from db.sources import create_source
from db.entries import create_entry, get_entry


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")


def _fake_feed(items):
    def _fetch(url):
        return items
    return _fetch


def test_backfill_fills_null_enclosure_url(source, monkeypatch):
    from scripts import backfill_enclosure_urls as bf
    e = create_entry(source_id=source["id"], title="Ep", url="https://example.com/ep",
                     guid="guid-ep")
    assert get_entry(e["id"])["enclosure_url"] is None
    monkeypatch.setattr(bf, "fetch_and_parse_feed", _fake_feed([
        {"guid": "guid-ep", "url": "https://example.com/ep",
         "enclosure_url": "https://cdn.example.com/ep.mp3"},
    ]))
    bf.backfill()
    assert get_entry(e["id"])["enclosure_url"] == "https://cdn.example.com/ep.mp3"


def test_backfill_leaves_existing_enclosure_url_untouched(source, monkeypatch):
    from scripts import backfill_enclosure_urls as bf
    e = create_entry(source_id=source["id"], title="Ep2", url="https://example.com/ep2",
                     guid="guid-ep2", enclosure_url="https://cdn.example.com/original.mp3")
    monkeypatch.setattr(bf, "fetch_and_parse_feed", _fake_feed([
        {"guid": "guid-ep2", "url": "https://example.com/ep2",
         "enclosure_url": "https://cdn.example.com/different.mp3"},
    ]))
    bf.backfill()
    assert get_entry(e["id"])["enclosure_url"] == "https://cdn.example.com/original.mp3"


def test_backfill_dry_run_does_not_write(source, monkeypatch):
    from scripts import backfill_enclosure_urls as bf
    e = create_entry(source_id=source["id"], title="Ep3", url="https://example.com/ep3",
                     guid="guid-ep3")
    monkeypatch.setattr(bf, "fetch_and_parse_feed", _fake_feed([
        {"guid": "guid-ep3", "url": "https://example.com/ep3",
         "enclosure_url": "https://cdn.example.com/ep3.mp3"},
    ]))
    bf.backfill(dry_run=True)
    assert get_entry(e["id"])["enclosure_url"] is None
