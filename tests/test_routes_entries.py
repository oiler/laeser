import pytest
from db.sources import create_source
from db.entries import create_entry


@pytest.fixture
def source():
    return create_source(name="Security Now", type="podcast",
                         feed_url="https://feeds.twit.tv/sn.xml",
                         archive_mode="full_archive", folder_name="security-now")


@pytest.fixture
def entry(source):
    return create_entry(source_id=source["id"], title="Ep 1047",
                        url="https://example.com/1047", description="Show notes.")


def test_entry_list_all(client, entry):
    resp = client.get("/entries")
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text


def test_entry_list_by_source(client, source, entry):
    resp = client.get(f"/entries?source_id={source['id']}")
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text


def test_entry_list_library_view(client, entry):
    # Before saving — should not appear in library
    resp = client.get("/entries?saved=1")
    assert "Ep 1047" not in resp.text


def test_entry_reader_renders(client, entry):
    resp = client.get(f"/entries/{entry['id']}")
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text
    assert "Show notes." in resp.text


def test_entry_reader_marks_as_read(client, entry):
    from db.entries import get_entry as db_get_entry
    assert db_get_entry(entry["id"])["read_at"] is None
    client.get(f"/entries/{entry['id']}")
    assert db_get_entry(entry["id"])["read_at"] is not None
