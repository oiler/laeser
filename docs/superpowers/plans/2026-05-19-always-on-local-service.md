# Always-On Local Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Laeser as a persistent, crash-restarting local service reachable at `http://app.laeser.org:8473`, surviving terminal close.

**Architecture:** A macOS launchd LaunchAgent supervises a no-reload `uvicorn` process bound to `127.0.0.1:8473`. No reverse proxy — uvicorn serves directly over loopback HTTP. A committed plist *template* plus an idempotent `install.sh` render the agent with machine-specific paths; a `laeserctl` wrapper drives `launchctl`.

**Tech Stack:** macOS launchd (`launchctl`), Bash, `uv`/uvicorn (existing app), `/etc/hosts`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `deploy/org.laeser.app.plist.template` | LaunchAgent definition with `__PLACEHOLDER__` tokens for machine-specific values |
| `deploy/install.sh` | One-time idempotent setup: render plist, create log dir, bootstrap agent, advise on `/etc/hosts` |
| `deploy/laeserctl` | Runtime wrapper over `launchctl` (start/stop/restart/status/logs) |
| `README.md` | Add a "Running as a service" section |

No `.py` files change — `WorkingDirectory` in the plist makes the relative `laeser.db` / `library/` paths resolve as they do today.

The `/etc/hosts` entry (`127.0.0.1 app.laeser.org`) is added by the user with `sudo`; no task edits that file.

---

### Task 1: LaunchAgent plist template

**Files:**
- Create: `deploy/org.laeser.app.plist.template`

- [ ] **Step 1: Create the plist template**

Create `deploy/org.laeser.app.plist.template` with exactly this content:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>org.laeser.app</string>
	<key>ProgramArguments</key>
	<array>
		<string>__UV_PATH__</string>
		<string>run</string>
		<string>uvicorn</string>
		<string>main:app</string>
		<string>--host</string>
		<string>127.0.0.1</string>
		<string>--port</string>
		<string>8473</string>
	</array>
	<key>WorkingDirectory</key>
	<string>__PROJECT_DIR__</string>
	<key>RunAtLoad</key>
	<false/>
	<key>KeepAlive</key>
	<dict>
		<key>SuccessfulExit</key>
		<false/>
	</dict>
	<key>StandardOutPath</key>
	<string>__LOG_DIR__/laeser.log</string>
	<key>StandardErrorPath</key>
	<string>__LOG_DIR__/laeser.log</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>__SERVICE_PATH__</string>
	</dict>
</dict>
</plist>
```

The four `__TOKEN__` values are substituted by `install.sh` in Task 3: `__UV_PATH__` (absolute path to `uv`), `__PROJECT_DIR__` (repo root), `__LOG_DIR__` (`~/Library/Logs/laeser`), `__SERVICE_PATH__` (a `PATH` value).

- [ ] **Step 2: Verify the template is well-formed XML**

Run: `plutil -lint deploy/org.laeser.app.plist.template`
Expected: `deploy/org.laeser.app.plist.template: OK`

(Placeholder tokens are valid `<string>` content, so the template lints clean even before rendering.)

- [ ] **Step 3: Commit**

```bash
git add deploy/org.laeser.app.plist.template
git commit -m "feat: add launchd plist template for local service"
```

---

### Task 2: `laeserctl` management wrapper

**Files:**
- Create: `deploy/laeserctl`

- [ ] **Step 1: Create the laeserctl script**

Create `deploy/laeserctl` with exactly this content:

```bash
#!/usr/bin/env bash
# Manage the Laeser launchd service.
set -euo pipefail

LABEL="org.laeser.app"
TARGET="gui/$(id -u)/${LABEL}"
LOG="${HOME}/Library/Logs/laeser/laeser.log"

case "${1:-}" in
	start)
		launchctl kickstart "$TARGET"
		echo "Started ${LABEL}"
		;;
	stop)
		launchctl kill SIGTERM "$TARGET"
		echo "Stopped ${LABEL}"
		;;
	restart)
		launchctl kill SIGTERM "$TARGET" 2>/dev/null || true
		sleep 1
		launchctl kickstart "$TARGET"
		echo "Restarted ${LABEL}"
		;;
	status)
		launchctl print "$TARGET"
		;;
	logs)
		tail -f "$LOG"
		;;
	*)
		echo "Usage: laeserctl {start|stop|restart|status|logs}" >&2
		exit 1
		;;
esac
```

`restart` tolerates an already-stopped service (`|| true`); after a clean SIGTERM the agent's `KeepAlive = { SuccessfulExit = false }` will *not* auto-restart it, so `restart` issues an explicit `kickstart`.

- [ ] **Step 2: Make it executable**

Run: `chmod +x deploy/laeserctl`

- [ ] **Step 3: Verify shell syntax**

Run: `bash -n deploy/laeserctl && deploy/laeserctl 2>&1; echo "exit=$?"`
Expected: prints `Usage: laeserctl {start|stop|restart|status|logs}` and `exit=1` (no args → usage message, non-zero exit; `bash -n` reports no syntax errors).

- [ ] **Step 4: Commit**

```bash
git add deploy/laeserctl
git commit -m "feat: add laeserctl service management wrapper"
```

---

### Task 3: `install.sh` setup script

**Files:**
- Create: `deploy/install.sh`

- [ ] **Step 1: Create the install script**

Create `deploy/install.sh` with exactly this content:

```bash
#!/usr/bin/env bash
# Idempotent one-time setup for the Laeser launchd service.
set -euo pipefail

LABEL="org.laeser.app"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${PROJECT_DIR}/deploy/org.laeser.app.plist.template"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST="${PLIST_DIR}/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/laeser"
TARGET="gui/$(id -u)/${LABEL}"

# 1. Locate uv.
UV_PATH="$(command -v uv || true)"
if [[ -z "$UV_PATH" ]]; then
	echo "Error: 'uv' not found on PATH. Install uv first." >&2
	exit 1
fi
SERVICE_PATH="$(dirname "$UV_PATH"):/usr/bin:/bin:/usr/sbin:/sbin"

# 2. Advise on the /etc/hosts entry (never edited here — needs sudo).
if ! grep -q 'app\.laeser\.org' /etc/hosts; then
	echo "NOTE: app.laeser.org is not in /etc/hosts. Add it with:"
	echo "    echo '127.0.0.1 app.laeser.org' | sudo tee -a /etc/hosts"
	echo
fi

# 3. Create the log directory.
mkdir -p "$LOG_DIR"

# 4. Render the plist template into ~/Library/LaunchAgents.
mkdir -p "$PLIST_DIR"
sed -e "s|__UV_PATH__|${UV_PATH}|g" \
    -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__LOG_DIR__|${LOG_DIR}|g" \
    -e "s|__SERVICE_PATH__|${SERVICE_PATH}|g" \
    "$TEMPLATE" > "$PLIST"
echo "Wrote ${PLIST}"

# 5. (Re-)bootstrap the LaunchAgent so launchd picks up the current plist.
launchctl bootout "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Bootstrapped ${LABEL} (loaded, not started)"

echo
echo "Setup complete. Start the service with:"
echo "    deploy/laeserctl start"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x deploy/install.sh`

- [ ] **Step 3: Verify shell syntax**

Run: `bash -n deploy/install.sh; echo "exit=$?"`
Expected: `exit=0` (no syntax errors). Do **not** execute it yet — full execution happens in Task 5.

- [ ] **Step 4: Commit**

```bash
git add deploy/install.sh
git commit -m "feat: add install.sh to set up the launchd service"
```

---

### Task 4: README "Running as a service" section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Append the service section to README.md**

After the existing "Running locally" section, add this content:

```markdown
## Running as a service

Laeser can run as an always-on local service supervised by macOS `launchd`, reachable at `http://app.laeser.org:8473`. It survives closing the terminal and restarts automatically if it crashes.

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

The service does not come back automatically after a reboot — start it again with `deploy/laeserctl start`.

**Do not run the dev instance (`uvicorn --reload`) and the service at the same time** — both open the same `laeser.db` and `library/`, and would run two schedulers and two download workers against shared state. Run one or the other.
```

- [ ] **Step 2: Verify the README renders the new section**

Run: `grep -n "Running as a service" README.md`
Expected: one matching line (the new section heading).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document running Laeser as a launchd service"
```

---

### Task 5: Install and verify end-to-end

This task runs the real setup and the spec's verification checklist. No commit unless a fix is needed.

- [ ] **Step 1: Confirm the hosts entry exists**

Run: `dscacheutil -q host -a name app.laeser.org`
Expected: output includes `ip_address: 127.0.0.1`.
If it does not resolve, add it: `echo '127.0.0.1 app.laeser.org' | sudo tee -a /etc/hosts`

- [ ] **Step 2: Run the installer**

Run: `deploy/install.sh`
Expected: prints `Wrote …/org.laeser.app.plist`, `Bootstrapped org.laeser.app (loaded, not started)`, and the "Setup complete" message.

- [ ] **Step 3: Confirm no dev instance is running**

Run: `pgrep -fl 'uvicorn main:app' || echo "none running"`
Expected: `none running`. If a dev instance is listed, stop it before continuing (shared `laeser.db`).

- [ ] **Step 4: Start the service**

Run: `deploy/laeserctl start`
Expected: `Started org.laeser.app`.

- [ ] **Step 5: Verify the app responds over the hostname**

Run: `sleep 2 && curl -s -o /dev/null -w "%{http_code}\n" http://app.laeser.org:8473/`
Expected: `200`.

- [ ] **Step 6: Verify crash-restart**

Run: `pkill -KILL -f 'uvicorn main:app' && sleep 3 && curl -s -o /dev/null -w "%{http_code}\n" http://app.laeser.org:8473/`
Expected: `200` — launchd restarted the killed process (`KeepAlive` on non-zero exit).

- [ ] **Step 7: Verify clean stop stays stopped**

Run: `deploy/laeserctl stop && sleep 3 && curl -s -o /dev/null -w "%{http_code}\n" http://app.laeser.org:8473/ ; echo "(curl exit above)"`
Expected: a non-200 result / connection failure — the service did not auto-restart after a clean SIGTERM.

- [ ] **Step 8: Verify status and logs work**

Run: `deploy/laeserctl start && sleep 2 && deploy/laeserctl status | grep -E 'state|pid'`
Expected: shows `state = running` and a `pid`.
Run: `tail -n 5 ~/Library/Logs/laeser/laeser.log`
Expected: recent uvicorn startup lines.

- [ ] **Step 9: Report results**

Summarize each verification step's outcome. The implementation is complete when steps 1–8 pass. Leave the service running (or stop it) per the user's preference.
```

---

## Postmortem (2026-05-19)

Task 5 step 7 failed in execution — `laeserctl stop` did not stay stopped. Root cause: the plan's `KeepAlive = { SuccessfulExit = false }` design assumed uvicorn exits 0 on a graceful SIGTERM. Empirical testing showed it exits **143** (= 128 + 15) regardless of how cleanly it shut down. That is indistinguishable from a crash, so launchd always restarts. The defect is exit-code-based: no condition on `KeepAlive` can tell stop from crash for this app.

**Corrected design** (now reflected in the spec, the three `deploy/` files, and `.gitignore` — superseding what Tasks 1–3 originally specified):

- Plist uses `KeepAlive = true` and **no** `RunAtLoad` key.
- `install.sh` renders the plist into **`deploy/org.laeser.app.plist`** (in the repo, gitignored), not `~/Library/LaunchAgents/`. It no longer bootstraps the agent; that is `laeserctl start`'s job. It does clean up any legacy plist left in `~/Library/LaunchAgents/` from this earlier mistake.
- `laeserctl` controls the service by **load state**, not signals: `start` → `bootstrap`; `stop` → `bootout`; `restart` → `bootout` then `bootstrap`. No more `kickstart`/`kill SIGTERM`.
- Keeping the plist out of `~/Library/LaunchAgents/` is what gives us "no reboot revival" — only that directory is auto-bootstrapped at login.

The corrected design was verified end-to-end before the task was marked done. The fix lives in commit history (search `fix: switch launchd control to load state`) and the spec doc has been updated.
