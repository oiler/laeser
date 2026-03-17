import pytest
from db.sources import create_source
from db.entries import (
    create_entry,
    get_entry,
    list_entries,
    mark_read,
    save_entry,
    search_entries,
    unsave_entry,
    update_entry_fetch_status,
)


@pytest.fixture
def source():
    return create_source(
        name="Security Now", type="podcast",
        feed_url="https://feeds.twit.tv/sn.xml",
        archive_mode="full_archive", folder_name="security-now",
    )


@pytest.fixture
def entry(source):
    return create_entry(
        source_id=source["id"], title="Episode 1047: XZ Backdoor",
        url="https://twit.tv/sn/1047", author="Steve Gibson",
        description="Show notes here", pub_date="2024-04-02",
    )


def test_create_entry(source):
    e = create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1")
    assert e["id"] is not None
    assert e["fetch_status"] == "pending"
    assert e["is_saved"] == 0
    assert e["source_name"] == "Security Now"


def test_create_entry_deduplicates_by_url(source, entry):
    create_entry(source_id=source["id"], title="Duplicate", url="https://twit.tv/sn/1047")
    entries = list_entries(source_id=source["id"])
    assert len(entries) == 1


def test_list_entries_for_source(source):
    create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1")
    create_entry(source_id=source["id"], title="Ep 2", url="https://example.com/2")
    assert len(list_entries(source_id=source["id"])) == 2


def test_list_entries_saved_only(source):
    e1 = create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1")
    create_entry(source_id=source["id"], title="Ep 2", url="https://example.com/2")
    save_entry(e1["id"], file_path="library/security-now/ep1.md")
    assert len(list_entries(saved_only=True)) == 1


def test_mark_read(entry):
    assert entry["read_at"] is None
    mark_read(entry["id"])
    assert get_entry(entry["id"])["read_at"] is not None


def test_mark_read_is_idempotent(entry):
    mark_read(entry["id"])
    first_read_at = get_entry(entry["id"])["read_at"]
    mark_read(entry["id"])
    assert get_entry(entry["id"])["read_at"] == first_read_at


def test_save_entry(entry):
    save_entry(entry["id"], file_path="library/security-now/ep1047.md")
    updated = get_entry(entry["id"])
    assert updated["is_saved"] == 1
    assert updated["file_path"] == "library/security-now/ep1047.md"


def test_unsave_preserves_file_path(entry):
    save_entry(entry["id"], file_path="library/security-now/ep1047.md")
    unsave_entry(entry["id"])
    updated = get_entry(entry["id"])
    assert updated["is_saved"] == 0
    assert updated["file_path"] == "library/security-now/ep1047.md"


def test_update_entry_fetch_status(entry):
    update_entry_fetch_status(entry["id"], "ok")
    assert get_entry(entry["id"])["fetch_status"] == "ok"


def test_search_by_title(source):
    create_entry(source_id=source["id"], title="XZ Backdoor Episode", url="https://example.com/1")
    create_entry(source_id=source["id"], title="TCP Episode", url="https://example.com/2")
    results = search_entries(query="XZ Backdoor")
    assert len(results) == 1
    assert results[0]["title"] == "XZ Backdoor Episode"


def test_search_by_description(source):
    create_entry(source_id=source["id"], title="Ep 1", url="https://example.com/1", description="backdoor vulnerability")
    create_entry(source_id=source["id"], title="Ep 2", url="https://example.com/2", description="networking basics")
    assert len(search_entries(query="vulnerability")) == 1


def test_search_filtered_by_source_ids(source):
    source2 = create_source(name="Other Show", type="rss", feed_url="https://other.com",
                             archive_mode="track_only", folder_name="other-show")
    create_entry(source_id=source["id"], title="Security XZ", url="https://example.com/1")
    create_entry(source_id=source2["id"], title="Security TCP", url="https://example.com/2")
    results = search_entries(query="Security", source_ids=[source["id"]])
    assert len(results) == 1
    assert results[0]["source_name"] == "Security Now"
