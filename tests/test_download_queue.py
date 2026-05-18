import pytest

from db.sources import create_source
from db.entries import create_entry, get_entry, set_audio_status


@pytest.fixture(autouse=True)
def _drain_queue():
    """The download queue is module-level state; drain it around every test."""
    import queue
    from feeds import download_queue
    # Ensure no worker is running from a previous test
    download_queue.stop_worker()
    # Reset the queue to clear any internal counter state
    download_queue._queue = queue.Queue()
    yield
    # Clean up after the test
    download_queue.stop_worker()
    # Reset the queue for the next test
    download_queue._queue = queue.Queue()


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")


def test_enqueue_sets_queued_status(source):
    from feeds.download_queue import enqueue
    e = create_entry(source_id=source["id"], title="Ep", url="https://example.com/e",
                     enclosure_url="https://cdn.example.com/e.mp3")
    enqueue(e["id"])
    assert get_entry(e["id"])["audio_status"] == "queued"


def test_process_download_success(source, monkeypatch):
    from feeds import download_queue
    e = create_entry(source_id=source["id"], title="Good Ep", pub_date="2026-05-01",
                     url="https://example.com/g", enclosure_url="https://cdn.example.com/g.mp3")
    monkeypatch.setattr(download_queue, "download_file", lambda url, dest: True)
    download_queue.process_download(e["id"])
    row = get_entry(e["id"])
    assert row["audio_status"] == "downloaded"
    assert row["audio_path"] == "security-now/2026-05-01-good-ep.mp3"


def test_process_download_failure(source, monkeypatch):
    from feeds import download_queue
    e = create_entry(source_id=source["id"], title="Bad Ep",
                     url="https://example.com/b", enclosure_url="https://cdn.example.com/b.mp3")
    monkeypatch.setattr(download_queue, "download_file", lambda url, dest: False)
    download_queue.process_download(e["id"])
    assert get_entry(e["id"])["audio_status"] == "failed"


def test_process_download_skips_entry_without_enclosure_url(source, monkeypatch):
    from feeds import download_queue
    e = create_entry(source_id=source["id"], title="No URL", url="https://example.com/nu")

    def _fail(url, dest):
        raise AssertionError("download_file should not be called")

    monkeypatch.setattr(download_queue, "download_file", _fail)
    download_queue.process_download(e["id"])
    assert get_entry(e["id"])["audio_status"] == "none"


def test_requeue_pending_enqueues_queued_and_downloading(source):
    from feeds import download_queue
    e1 = create_entry(source_id=source["id"], title="Q", url="https://example.com/q",
                      enclosure_url="https://cdn.example.com/q.mp3")
    e2 = create_entry(source_id=source["id"], title="D", url="https://example.com/d",
                      enclosure_url="https://cdn.example.com/d.mp3")
    set_audio_status(e1["id"], "queued")
    set_audio_status(e2["id"], "downloading")
    download_queue._requeue_pending()
    requeued = set()
    while not download_queue._queue.empty():
        requeued.add(download_queue._queue.get_nowait())
    assert requeued == {e1["id"], e2["id"]}


def test_worker_processes_enqueued_entry(source, monkeypatch):
    from feeds import download_queue
    monkeypatch.setattr(download_queue, "download_file", lambda url, dest: True)
    download_queue.start_worker()
    try:
        e = create_entry(source_id=source["id"], title="Worker Ep", pub_date="2026-05-01",
                         url="https://example.com/w", enclosure_url="https://cdn.example.com/w.mp3")
        download_queue.enqueue(e["id"])
        download_queue._queue.join()
        assert get_entry(e["id"])["audio_status"] == "downloaded"
    finally:
        download_queue.stop_worker()
