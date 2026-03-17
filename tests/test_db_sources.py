import pytest
from db.sources import (
    create_source,
    delete_source,
    get_source,
    list_sources,
    list_sources_with_unread_count,
    update_source_fetch_status,
)


def _make_source(**kwargs):
    defaults = dict(
        name="Security Now",
        type="podcast",
        feed_url="https://feeds.twit.tv/sn.xml",
        archive_mode="full_archive",
        folder_name="security-now",
    )
    defaults.update(kwargs)
    return create_source(**defaults)


def test_create_source():
    source = _make_source()
    assert source["id"] is not None
    assert source["name"] == "Security Now"
    assert source["archive_mode"] == "full_archive"
    assert source["last_fetch_error"] is None


def test_list_sources_includes_manual():
    sources = list_sources()
    names = [s["name"] for s in sources]
    assert "Manual Entries" in names


def test_create_duplicate_folder_name_raises():
    _make_source(folder_name="my-show", name="Show A")
    with pytest.raises(Exception):
        _make_source(folder_name="my-show", name="Show B")


def test_get_source():
    source = _make_source(name="In Our Time", folder_name="in-our-time")
    fetched = get_source(source["id"])
    assert fetched["name"] == "In Our Time"


def test_get_source_returns_none_for_missing():
    assert get_source(9999) is None


def test_delete_source():
    source = _make_source(folder_name="temp-show", name="Temp")
    delete_source(source["id"])
    assert get_source(source["id"]) is None


def test_update_source_fetch_status_success():
    source = _make_source()
    update_source_fetch_status(source["id"], error=None)
    updated = get_source(source["id"])
    assert updated["last_fetched_at"] is not None
    assert updated["last_fetch_error"] is None


def test_update_source_fetch_status_error():
    source = _make_source()
    update_source_fetch_status(source["id"], error="Connection refused")
    updated = get_source(source["id"])
    assert updated["last_fetch_error"] == "Connection refused"
    assert updated["last_fetched_at"] is not None


def test_list_sources_with_unread_count():
    sources = list_sources_with_unread_count()
    assert all("unread_count" in s for s in sources)
