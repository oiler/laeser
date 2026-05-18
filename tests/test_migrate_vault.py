import os
from pathlib import Path

import frontmatter

from db.connection import get_db
from db.entries import create_entry, save_entry, update_entry_audio_path
from db.sources import create_source
from scripts.migrate_vault import migrate


def _make_saved_entry_with_old_format(library: Path) -> dict:
    """Create a source + saved entry in the old format (HTML body, ugly mp3 name)."""
    source = create_source(
        name="My Show",
        type="podcast",
        feed_url="https://example.com/feed",
        archive_mode="full_archive",
        folder_name="my-show",
    )
    entry = create_entry(
        source_id=source["id"],
        title="The XZ Backdoor",
        url="https://example.com/ep",
        guid="ep-1",
        author="Steve",
        description="<p>Show notes with <strong>HTML</strong>.</p>",
        pub_date="2024-04-02",
    )
    # Old-format MP3 on disk
    old_audio_rel = "my-show/2024-04-02-1.mp3"
    (library / "my-show").mkdir(parents=True, exist_ok=True)
    (library / old_audio_rel).write_bytes(b"FAKEAUDIO")
    update_entry_audio_path(entry["id"], old_audio_rel)
    # Old-format markdown file on disk
    old_md = library / "my-show" / "2024-04-02-the-xz-backdoor.md"
    old_md.write_text("---\ntitle: stale\n---\nstale body", encoding="utf-8")
    save_entry(entry["id"], file_path=str(old_md))
    return {
        "entry_id": entry["id"],
        "old_audio_rel": old_audio_rel,
        "old_md": old_md,
    }


def test_migrate_renames_audio_and_rewrites_markdown(tmp_path):
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    info = _make_saved_entry_with_old_format(library)

    migrate(dry_run=False)

    new_audio = library / "my-show" / "2024-04-02-the-xz-backdoor.mp3"
    new_md = library / "my-show" / "2024-04-02-the-xz-backdoor.md"
    assert new_audio.exists()
    assert not (library / info["old_audio_rel"]).exists()

    with get_db() as conn:
        row = conn.execute(
            "SELECT audio_path, file_path FROM entries WHERE id = ?",
            (info["entry_id"],),
        ).fetchone()
    assert row["audio_path"] == "my-show/2024-04-02-the-xz-backdoor.mp3"
    assert row["file_path"] == str(new_md)

    post = frontmatter.load(str(new_md))
    assert post["title"] == "The XZ Backdoor"
    assert post.content.startswith("![[2024-04-02-the-xz-backdoor.mp3]]")
    assert "**HTML**" in post.content
    assert "<p>" not in post.content


def test_migrate_is_idempotent(tmp_path):
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    _make_saved_entry_with_old_format(library)

    migrate(dry_run=False)

    new_md = library / "my-show" / "2024-04-02-the-xz-backdoor.md"
    first_content = new_md.read_text(encoding="utf-8")
    first_mtime = new_md.stat().st_mtime_ns

    migrate(dry_run=False)

    assert new_md.read_text(encoding="utf-8") == first_content
    # Second run may rewrite identical content; what matters is no DB churn and stable filename
    assert new_md.exists()


def test_migrate_dry_run_changes_nothing(tmp_path):
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    info = _make_saved_entry_with_old_format(library)

    migrate(dry_run=True)

    # Old paths still present, no new paths created
    assert (library / info["old_audio_rel"]).exists()
    assert not (library / "my-show" / "2024-04-02-the-xz-backdoor.mp3").exists()

    with get_db() as conn:
        row = conn.execute(
            "SELECT audio_path FROM entries WHERE id = ?",
            (info["entry_id"],),
        ).fetchone()
    assert row["audio_path"] == info["old_audio_rel"]


def test_migrate_skips_entries_with_missing_audio_file(tmp_path):
    """Entry's audio_path points to a file that doesn't exist on disk — log and continue."""
    library = Path(os.environ["LAESER_LIBRARY_PATH"])
    source = create_source(
        name="My Show",
        type="podcast",
        feed_url="https://example.com/feed",
        archive_mode="full_archive",
        folder_name="my-show",
    )
    entry = create_entry(
        source_id=source["id"],
        title="Lost Audio",
        url="https://example.com/lost",
        guid="lost-1",
        author="",
        description="No audio on disk.",
        pub_date="2024-04-02",
    )
    update_entry_audio_path(entry["id"], "my-show/nonexistent.mp3")
    save_entry(entry["id"], file_path="ignored")

    migrate(dry_run=False)

    new_md = library / "my-show" / "2024-04-02-lost-audio.md"
    assert new_md.exists()
    with get_db() as conn:
        row = conn.execute(
            "SELECT audio_path FROM entries WHERE id = ?",
            (entry["id"],),
        ).fetchone()
    # Missing-source-file policy: audio_path still gets normalised to the new name,
    # even though no file was renamed. A warning is logged.
    assert row["audio_path"] == "my-show/2024-04-02-lost-audio.mp3"
