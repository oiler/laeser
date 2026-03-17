import os
from pathlib import Path
import frontmatter
from storage import write_entry_file, slugify


def test_slugify():
    assert slugify("Hello World!") == "hello-world"
    assert slugify("The XZ Backdoor (2024)") == "the-xz-backdoor-2024"
    assert slugify("A" * 100)[:80] == slugify("A" * 100)  # truncated to 80 chars


def test_write_entry_file_creates_file(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Security Now 1047: XZ Backdoor",
        "source_name": "Security Now",
        "source_folder": "security-now",
        "author": "Steve Gibson",
        "pub_date": "2024-04-02",
        "url": "https://twit.tv/sn/1047",
        "audio_path": "",
        "description": "Show notes here.",
        "tags": [],
    }
    path = write_entry_file(entry)
    assert path.exists()
    assert path.suffix == ".md"
    assert "security-now" in str(path)


def test_write_entry_file_frontmatter(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Test Episode",
        "source_name": "My Show",
        "source_folder": "my-show",
        "author": "Author Name",
        "pub_date": "2024-01-15",
        "url": "https://example.com/ep",
        "audio_path": "library/my-show/ep.mp3",
        "description": "Episode description.",
        "tags": ["security", "networking"],
    }
    path = write_entry_file(entry)
    post = frontmatter.load(str(path))
    assert post["title"] == "Test Episode"
    assert post["source"] == "My Show"
    assert post["author"] == "Author Name"
    assert post["pub_date"] == "2024-01-15"
    assert post["url"] == "https://example.com/ep"
    assert post["audio_path"] == "library/my-show/ep.mp3"
    assert post["tags"] == ["security", "networking"]
    assert post.content == "Episode description."


def test_write_entry_file_overwrites_on_resave(tmp_path):
    os.environ["LAESER_LIBRARY_PATH"] = str(tmp_path)
    entry = {
        "title": "Test Episode", "source_name": "My Show", "source_folder": "my-show",
        "author": "", "pub_date": "2024-01-15", "url": "https://example.com/ep",
        "audio_path": "", "description": "First save.", "tags": [],
    }
    path1 = write_entry_file(entry)
    entry["description"] = "Updated save."
    path2 = write_entry_file(entry)
    assert path1 == path2
    post = frontmatter.load(str(path2))
    assert post.content == "Updated save."
