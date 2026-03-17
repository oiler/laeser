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


def test_save_entry(client, entry):
    resp = client.post(f"/entries/{entry['id']}/save")
    assert resp.status_code == 200
    assert "★" in resp.text  # saved star shown
    from db.entries import get_entry as db_get
    assert db_get(entry["id"])["is_saved"] == 1


def test_unsave_entry(client, entry):
    client.post(f"/entries/{entry['id']}/save")
    resp = client.post(f"/entries/{entry['id']}/unsave")
    assert resp.status_code == 200
    assert "☆" in resp.text


def test_add_tag_to_entry(client, entry):
    resp = client.post(f"/entries/{entry['id']}/tags", data={"tag_name": "security"})
    assert resp.status_code == 200
    assert "security" in resp.text


def test_remove_tag_from_entry(client, entry):
    from db.tags import create_tag, add_tag_to_entry
    tag = create_tag("networking")
    add_tag_to_entry(entry["id"], tag["id"])
    resp = client.delete(f"/entries/{entry['id']}/tags/{tag['id']}")
    assert resp.status_code == 200
    assert "networking" not in resp.text
