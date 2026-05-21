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


def test_save_bulk_saves_multiple(client, source):
    from db.entries import create_entry, get_entry as db_get
    e1 = create_entry(source_id=source["id"], title="Bulk A",
                      url="https://example.com/a", description="A")
    e2 = create_entry(source_id=source["id"], title="Bulk B",
                      url="https://example.com/b", description="B")
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert "Bulk A" in resp.text and "Bulk B" in resp.text
    assert db_get(e1["id"])["is_saved"] == 1
    assert db_get(e2["id"])["is_saved"] == 1


def test_save_bulk_skips_already_saved(client, source):
    from db.entries import create_entry, get_entry as db_get
    e1 = create_entry(source_id=source["id"], title="Already",
                      url="https://example.com/c", description="C")
    client.post(f"/entries/{e1['id']}/save")
    saved_path = db_get(e1["id"])["file_path"]
    # Bulk-saving an already-saved entry must not change it.
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e1["id"])["file_path"] == saved_path


def test_save_bulk_empty_selection(client, entry):
    resp = client.post("/entries/save-bulk", data={"sort": "desc"})
    assert resp.status_code == 200
    assert "Ep 1047" in resp.text  # list still renders


def test_entry_list_has_checkboxes(client, entry):
    resp = client.get("/entries")
    assert 'class="entry-checkbox"' in resp.text
    assert 'id="select-all"' in resp.text


def test_saved_entry_row_has_saved_class(client, entry):
    resp = client.get("/entries")
    assert "entry-row unread" in resp.text  # unsaved, no saved class
    client.post(f"/entries/{entry['id']}/save")
    resp = client.get("/entries")
    assert "entry-row unread saved" in resp.text  # row now carries the saved class


def test_save_bulk_preserves_source_id(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Filtered",
                      url="https://example.com/f", description="F")
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"]], "source_id": source["id"], "sort": "desc"})
    assert resp.status_code == 200
    assert "Filtered" in resp.text


def test_download_bulk_enqueues_eligible_entries(client, source):
    from db.entries import create_entry, get_entry as db_get
    e1 = create_entry(source_id=source["id"], title="DL A", url="https://example.com/dla",
                      enclosure_url="https://cdn.example.com/dla.mp3")
    e2 = create_entry(source_id=source["id"], title="DL B", url="https://example.com/dlb",
                      enclosure_url="https://cdn.example.com/dlb.mp3")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e1["id"])["audio_status"] == "queued"
    assert db_get(e2["id"])["audio_status"] == "queued"


def test_download_bulk_skips_entry_without_enclosure_url(client, source):
    from db.entries import create_entry, get_entry as db_get
    e = create_entry(source_id=source["id"], title="No Enclosure", url="https://example.com/ne")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e["id"])["audio_status"] == "none"


def test_download_bulk_skips_already_downloaded(client, source):
    from db.entries import create_entry, get_entry as db_get
    from db.entries import update_entry_audio_path, set_audio_status
    e = create_entry(source_id=source["id"], title="Done", url="https://example.com/done",
                     enclosure_url="https://cdn.example.com/done.mp3")
    update_entry_audio_path(e["id"], "security-now/done.mp3")
    set_audio_status(e["id"], "downloaded")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert db_get(e["id"])["audio_status"] == "downloaded"


def test_toolbar_has_download_button(client, entry):
    resp = client.get("/entries")
    assert 'hx-post="/entries/download-bulk"' in resp.text
    assert "Download audio" in resp.text


def test_entry_list_shows_download_status_icons(client, source):
    from db.entries import create_entry, set_audio_status
    e = create_entry(source_id=source["id"], title="Queued Ep", url="https://example.com/qe")
    set_audio_status(e["id"], "queued")
    resp = client.get("/entries")
    assert "Audio download queued" in resp.text


import re


def _checkbox_is_checked(html: str, entry_id: int) -> bool:
    """True iff the <input> for this entry id includes the `checked` attribute."""
    pattern = re.compile(
        r'<input[^>]*\bvalue="' + str(entry_id) + r'"[^>]*>',
        re.IGNORECASE,
    )
    match = pattern.search(html)
    if not match:
        return False
    return "checked" in match.group(0)


def test_entry_list_get_renders_checkboxes_unchecked(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Plain A",
                      url="https://example.com/plain-a", description="A")
    resp = client.get("/entries")
    assert resp.status_code == 200
    assert not _checkbox_is_checked(resp.text, e1["id"])


def test_save_bulk_preserves_selection_in_response(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Sel A",
                      url="https://example.com/sel-a", description="A")
    e2 = create_entry(source_id=source["id"], title="Sel B",
                      url="https://example.com/sel-b", description="B")
    resp = client.post("/entries/save-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert _checkbox_is_checked(resp.text, e1["id"])
    assert _checkbox_is_checked(resp.text, e2["id"])


def test_download_bulk_preserves_selection_in_response(client, source):
    from db.entries import create_entry
    e1 = create_entry(source_id=source["id"], title="Pod A",
                      url="https://example.com/pod-a", description="A",
                      enclosure_url="https://example.com/a.mp3")
    e2 = create_entry(source_id=source["id"], title="Pod B",
                      url="https://example.com/pod-b", description="B",
                      enclosure_url="https://example.com/b.mp3")
    resp = client.post("/entries/download-bulk",
                       data={"entry_ids": [e1["id"], e2["id"]], "sort": "desc"})
    assert resp.status_code == 200
    assert _checkbox_is_checked(resp.text, e1["id"])
    assert _checkbox_is_checked(resp.text, e2["id"])
