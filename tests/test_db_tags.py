import pytest
from db.sources import create_source
from db.entries import create_entry
from db.tags import add_tag_to_entry, create_tag, get_entry_tags, list_tags, remove_tag_from_entry


@pytest.fixture
def entry():
    s = create_source(name="Show", type="rss", feed_url="https://example.com",
                      archive_mode="track_only", folder_name="show")
    return create_entry(source_id=s["id"], title="Ep 1", url="https://example.com/1")


def test_create_tag():
    tag = create_tag("security")
    assert tag["name"] == "security"
    assert tag["id"] is not None


def test_create_tag_is_idempotent():
    t1 = create_tag("networking")
    t2 = create_tag("networking")
    assert t1["id"] == t2["id"]


def test_add_and_get_tags(entry):
    tag = create_tag("security")
    add_tag_to_entry(entry["id"], tag["id"])
    tags = get_entry_tags(entry["id"])
    assert len(tags) == 1
    assert tags[0]["name"] == "security"


def test_remove_tag(entry):
    tag = create_tag("security")
    add_tag_to_entry(entry["id"], tag["id"])
    remove_tag_from_entry(entry["id"], tag["id"])
    assert get_entry_tags(entry["id"]) == []


def test_add_tag_is_idempotent(entry):
    tag = create_tag("security")
    add_tag_to_entry(entry["id"], tag["id"])
    add_tag_to_entry(entry["id"], tag["id"])  # no error
    assert len(get_entry_tags(entry["id"])) == 1


def test_list_tags():
    create_tag("security")
    create_tag("networking")
    names = [t["name"] for t in list_tags()]
    assert "security" in names
    assert "networking" in names
