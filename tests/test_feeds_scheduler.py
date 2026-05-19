import pytest

from db.sources import create_source
from db.entries import create_entry, get_entry


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                          feed_url="https://feeds.twit.tv/sn.xml",
                          archive_mode="full_archive", folder_name="security-now")


def test_download_audio_sets_downloaded_status(source, monkeypatch):
    from feeds import scheduler
    e = create_entry(source_id=source["id"], title="Sched Ep", pub_date="2026-05-01",
                     url="https://example.com/se")
    monkeypatch.setattr(scheduler, "download_file", lambda url, dest, delay_seconds=3: True)
    scheduler._download_audio(get_entry(e["id"]), "https://cdn.example.com/se.mp3", "security-now")
    row = get_entry(e["id"])
    assert row["audio_status"] == "downloaded"
    assert row["audio_path"] == "security-now/2026-05-01-sched-ep.mp3"
