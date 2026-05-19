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

## Running as a service

Laeser can run as an always-on local service supervised by macOS `launchd`,
reachable at `http://app.laeser.org:8473`. It survives closing the terminal
and restarts automatically if it crashes.

### One-time setup

1. Map the hostname to loopback (needs `sudo`):

   ```sh
   echo '127.0.0.1 app.laeser.org' | sudo tee -a /etc/hosts
   ```

2. Install the LaunchAgent:

   ```sh
   deploy/install.sh
   ```

### Managing the service

```sh
deploy/laeserctl start     # start it (survives terminal close)
deploy/laeserctl stop      # stop it cleanly (stays stopped)
deploy/laeserctl restart   # restart
deploy/laeserctl status    # show launchd state
deploy/laeserctl logs      # tail the log
```

Then open http://app.laeser.org:8473 in your browser.

The service does not come back automatically after a reboot — start it again
with `deploy/laeserctl start`.

**Do not run the dev instance (`uvicorn --reload`) and the service at the same
time** — both open the same `laeser.db` and `library/`, and would run two
schedulers and two download workers against shared state. Run one or the other.
