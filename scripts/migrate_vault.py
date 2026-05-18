"""
One-shot migration: upgrade existing saved entries to the Obsidian-friendly
format introduced in May 2026 — Markdown bodies, date-slug audio filenames,
and inline audio embeds.

Run with the web app stopped to avoid serving an audio file that's mid-rename.

Usage:
    uv run python -m scripts.migrate_vault           # apply
    uv run python -m scripts.migrate_vault --dry-run # preview
"""
import argparse
import logging
import os
from pathlib import Path

from db.connection import get_db
from db.entries import update_entry_audio_path, save_entry
from naming import entry_base
from storage import get_library_path, write_entry_file

logger = logging.getLogger("migrate_vault")


def _saved_entries() -> list[dict]:
    sql = """
        SELECT e.*, s.name AS source_name, s.folder_name AS source_folder
        FROM entries e
        JOIN sources s ON s.id = e.source_id
        WHERE e.is_saved = 1
    """
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql).fetchall()]


def _entry_tags(entry_id: int) -> list[str]:
    sql = """
        SELECT t.name FROM tags t
        JOIN entry_tags et ON et.tag_id = t.id
        WHERE et.entry_id = ?
        ORDER BY t.name
    """
    with get_db() as conn:
        return [r["name"] for r in conn.execute(sql, (entry_id,)).fetchall()]


def _migrate_one(row: dict, library: Path, dry_run: bool) -> None:
    base = entry_base(row["title"], row.get("pub_date"))
    source_folder = row["source_folder"]

    # ---- audio ----
    current_audio_rel = row.get("audio_path") or ""
    new_audio_rel = ""
    if current_audio_rel:
        ext = Path(current_audio_rel).suffix.lstrip(".") or "mp3"
        new_audio_rel = f"{source_folder}/{base}.{ext}"
        current_audio_abs = library / current_audio_rel
        new_audio_abs = library / new_audio_rel

        if current_audio_rel != new_audio_rel:
            if current_audio_abs.exists():
                if dry_run:
                    logger.info(f"DRY-RUN rename: {current_audio_rel} -> {new_audio_rel}")
                else:
                    new_audio_abs.parent.mkdir(parents=True, exist_ok=True)
                    current_audio_abs.rename(new_audio_abs)
                    logger.info(f"renamed: {current_audio_rel} -> {new_audio_rel}")
            else:
                logger.warning(
                    f"audio file missing for entry {row['id']}: {current_audio_rel}"
                )
        if not dry_run:
            update_entry_audio_path(row["id"], new_audio_rel)

    # ---- markdown ----
    new_md_rel = f"{source_folder}/{base}.md"
    new_md_abs = library / new_md_rel
    old_md_abs = Path(row["file_path"]) if row.get("file_path") else None

    entry_dict = {
        "title": row["title"],
        "source_name": row["source_name"],
        "source_folder": source_folder,
        "author": row.get("author") or "",
        "pub_date": row.get("pub_date") or "",
        "url": row.get("url") or "",
        "audio_path": new_audio_rel,
        "description": row.get("description") or "",
        "tags": _entry_tags(row["id"]),
    }

    if dry_run:
        logger.info(f"DRY-RUN rewrite: {new_md_rel}")
        if old_md_abs and old_md_abs.exists() and old_md_abs != new_md_abs:
            logger.info(f"DRY-RUN delete stale: {old_md_abs}")
        return

    written = write_entry_file(entry_dict)
    save_entry(row["id"], file_path=str(written))
    logger.info(f"wrote: {new_md_rel}")

    if old_md_abs and old_md_abs.exists() and old_md_abs != written:
        old_md_abs.unlink()
        logger.info(f"deleted stale: {old_md_abs}")


def migrate(dry_run: bool = False) -> None:
    library = get_library_path()
    rows = _saved_entries()
    logger.info(f"Migrating {len(rows)} saved entries (dry_run={dry_run})")
    for row in rows:
        try:
            _migrate_one(row, library, dry_run)
        except Exception as exc:
            logger.error(f"entry {row['id']} failed: {exc}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without touching disk or DB.",
    )
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
