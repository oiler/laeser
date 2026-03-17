import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from feeds.downloader import download_file


def _mock_response(status_code=200, content=b"audio data", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.iter_content = lambda chunk_size: [content]
    resp.raise_for_status = MagicMock()
    return resp


def test_download_file_success(tmp_path):
    dest = tmp_path / "ep.mp3"
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(200)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is True
    assert dest.exists()
    assert dest.read_bytes() == b"audio data"


def test_download_file_404_returns_false(tmp_path):
    dest = tmp_path / "ep.mp3"
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(404)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is False
    assert not dest.exists()


def test_download_file_416_returns_true(tmp_path):
    """416 = Range Not Satisfiable = file already complete."""
    dest = tmp_path / "ep.mp3"
    dest.write_bytes(b"existing content")
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(416)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is True


def test_download_file_resumes_partial(tmp_path):
    dest = tmp_path / "ep.mp3"
    dest.write_bytes(b"partial")
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.return_value = _mock_response(206)
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is True
    # Verify Range header was sent
    call_kwargs = mock_get.call_args[1]
    assert "Range" in call_kwargs.get("headers", {})


def test_download_file_cleans_up_on_fresh_failure(tmp_path):
    dest = tmp_path / "ep.mp3"
    with patch("feeds.downloader.requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        result = download_file("https://example.com/ep.mp3", dest, delay_seconds=0)
    assert result is False
    assert not dest.exists()
