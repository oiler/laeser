# Laeser

Laeser is the software behind [laeser.org](https://laeser.org): a self-hosted service that lets you run your own RSS and podcast reader. It archives what you read as you go — MP3 files saved to disk, articles saved as Markdown. Your library is yours, and it outlives the feeds it came from.

## Features

- Reads RSS and podcast feeds, deduplicated by GUID so feeds with rotating access-token URLs don't produce duplicates
- Saves entries as Markdown notes with an embedded audio player at the top
- The library is a valid Obsidian vault — audio files and their notes share a `YYYY-MM-DD-slug` basename so `![[ ]]` embeds resolve
- Bulk episode selection with select-all and Shift+click ranges, plus bulk save and bulk audio download
- Polls feeds every 6 hours in the background
- A single sequential worker drains the audio download queue: polite to hosts, and interrupted batches resume on restart

## Install & run

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv run uvicorn main:app --reload
```

Then open http://127.0.0.1:8000 and add your feeds through the web interface.

## Configuration & usage

Your library lives in `library/` — one folder per source, with Markdown notes and downloaded audio side by side. Point it somewhere else with the `LAESER_LIBRARY_PATH` environment variable. Open the folder in Obsidian and it works as a vault with no extra setup.

The feed refresh interval is currently fixed at 6 hours.

The `scripts/` directory holds one-shot maintenance tools:

- `migrate_vault.py` — upgrades saved entries created before vault compatibility
- `backfill_enclosure_urls.py` — stores audio URLs for episodes downloaded before URLs were tracked
