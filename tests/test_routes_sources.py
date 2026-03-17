import pytest
from db.sources import create_source


def test_homepage_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Laeser" in resp.text


def test_add_source_via_post(client, mocker):
    mocker.patch("routes.sources.do_refresh")
    resp = client.post("/sources", data={
        "feed_url": "https://feeds.twit.tv/sn.xml",
        "name": "Security Now",
        "type": "podcast",
        "archive_mode": "full_archive",
    })
    assert resp.status_code == 200
    # Response is the refreshed sidebar HTML
    assert "Security Now" in resp.text


def test_add_source_returns_sidebar(client, mocker):
    mocker.patch("routes.sources.do_refresh")
    resp = client.post("/sources", data={
        "feed_url": "https://example.com/feed.rss",
        "name": "My Show",
        "type": "rss",
        "archive_mode": "track_only",
    })
    assert "My Show" in resp.text


def test_delete_source(client):
    source = create_source(name="To Delete", type="rss",
                           feed_url="https://example.com", archive_mode="track_only",
                           folder_name="to-delete")
    resp = client.delete(f"/sources/{source['id']}")
    assert resp.status_code == 200
    assert "To Delete" not in resp.text


def test_get_add_source_form(client):
    resp = client.get("/sources/add-form")
    assert resp.status_code == 200
    assert "Feed URL" in resp.text
