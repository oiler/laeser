import pytest
from db.sources import create_source
from db.entries import create_entry


@pytest.fixture
def populated_db():
    s = create_source(name="Security Now", type="podcast",
                      feed_url="https://feeds.twit.tv/sn.xml",
                      archive_mode="full_archive", folder_name="security-now")
    create_entry(source_id=s["id"], title="XZ Backdoor Episode",
                 url="https://example.com/1", description="security vulnerability")
    create_entry(source_id=s["id"], title="TCP Fundamentals",
                 url="https://example.com/2", description="networking basics")
    return s


def test_search_returns_results(client, populated_db):
    resp = client.get("/search?q=XZ+Backdoor")
    assert resp.status_code == 200
    assert "XZ Backdoor Episode" in resp.text
    assert "TCP Fundamentals" not in resp.text


def test_search_no_results(client, populated_db):
    resp = client.get("/search?q=quantum+computing")
    assert resp.status_code == 200
    assert "No entries found" in resp.text


def test_search_filtered_by_source(client, populated_db):
    s2 = create_source(name="Other Show", type="rss", feed_url="https://other.com",
                       archive_mode="track_only", folder_name="other-show")
    create_entry(source_id=s2["id"], title="XZ on Other Show",
                 url="https://other.com/1")
    resp = client.get(f"/search?q=XZ&source_id={populated_db['id']}")
    assert "XZ Backdoor Episode" in resp.text
    assert "XZ on Other Show" not in resp.text


def test_search_empty_query_returns_all(client, populated_db):
    resp = client.get("/search?q=")
    assert resp.status_code == 200
