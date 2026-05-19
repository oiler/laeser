# Always-On Local Service — Design

**Date:** 2026-05-19
**Status:** Approved

## Goal

Run Laeser as a persistent local service on the user's Mac, reachable at
`http://app.laeser.org:8473` instead of `http://127.0.0.1:8000`. The app must
survive closing the terminal that started it and restart automatically on
crash. This is *not* a remote/hosted deployment — the app stays bound to
loopback and accessible only from this machine.

## Constraints & decisions

- **Local only.** No remote hosting, no public exposure. Same trust model as
  today (single user, no authentication).
- **Manual start.** The service is started by an explicit command. It survives
  terminal close and restarts on crash, but does *not* come back on its own
  after a reboot (`RunAtLoad = false`).
- **No reverse proxy.** Ports 80/443 are held by Local by Flywheel's router
  (a wildcard `*:443` bind), which cannot be displaced without breaking the
  user's WordPress workflow. Laeser is therefore served directly by uvicorn
  over plain HTTP. Acceptable because traffic never leaves the loopback
  interface.
- **Port `8473`.** Chosen to avoid the common dev range (3000/5000/8000/8080/
  8888) and anything currently listening on the machine. Defined in exactly
  one place (the launchd plist).
- **`/etc/hosts` is owned by the user.** `install.sh` does not modify it; it
  detects the entry and prints the line to add if missing.

## Architecture

```
browser ──http──> uvicorn 127.0.0.1:8473 ──> Laeser app
   (http://app.laeser.org:8473)
```

Two independent units, plus supporting scripts:

1. **Hosts entry** — maps `app.laeser.org` to `127.0.0.1`. User-managed.
2. **launchd LaunchAgent** — supervises the uvicorn process.
3. **`install.sh`** — one-time, idempotent setup.
4. **`laeserctl`** — runtime management wrapper.

## Component 1: Domain resolution

A single line in `/etc/hosts`:

```
127.0.0.1 app.laeser.org
```

Added by the user (requires `sudo`). The skill cannot and does not edit
`/etc/hosts`.

Note: `laeser.org` is a real public `.org` domain. This entry shadows
`app.laeser.org` *on this machine only*. If the user ever registers the real
domain and needs to reach a remote `app.` subdomain from this Mac, the line
must be removed.

## Component 2: launchd LaunchAgent

A plist installed to `~/Library/LaunchAgents/org.laeser.app.plist`.

| Setting | Value |
|---|---|
| `Label` | `org.laeser.app` |
| `ProgramArguments` | `<uv> run uvicorn main:app --host 127.0.0.1 --port 8473` |
| `WorkingDirectory` | absolute path to the project directory |
| `RunAtLoad` | `false` |
| `KeepAlive` | `{ SuccessfulExit = false }` |
| `StandardOutPath` / `StandardErrorPath` | `~/Library/Logs/laeser/laeser.log` |
| `EnvironmentVariables` | `PATH` set to a sane value so `uv`/Python resolve |

Rationale:

- **No `--reload`** — reload is a dev convenience and watches the filesystem
  needlessly for a service.
- **`--host 127.0.0.1`** — loopback only; never exposed to the LAN.
- **`WorkingDirectory`** — the app uses relative paths for `laeser.db` and
  `library/` (`db/connection.py:11`, `storage.py:13`). Setting the working
  directory makes them resolve exactly as they do today. No `.py` changes
  required.
- **`RunAtLoad = false`** — after login the agent is auto-bootstrapped (loaded)
  but idle, so the app does not come back after a reboot until started
  manually. Matches the "manual start" decision.
- **`KeepAlive = { SuccessfulExit = false }`** — restarts the process only if
  it exits non-zero (a crash). A clean stop (SIGTERM → exit 0) leaves it down.

The plist is committed to the repo as a **template**
(`deploy/org.laeser.app.plist.template`) with `__PLACEHOLDER__` tokens for the
machine-specific values (`__UV_PATH__`, `__PROJECT_DIR__`, `__LOG_DIR__`), so
no hardcoded home path enters version control.

## Component 3: `deploy/install.sh`

Idempotent one-time setup. Safe to re-run. Steps:

1. Detect the `uv` binary (`command -v uv`) and the project directory.
2. Check `/etc/hosts` for `app.laeser.org`. If absent, print the exact line
   and the command to add it; do **not** edit the file.
3. Create `~/Library/Logs/laeser/`.
4. Render `org.laeser.app.plist.template` → `~/Library/LaunchAgents/org.laeser.app.plist`,
   substituting the placeholder tokens.
5. `launchctl bootstrap gui/$UID ~/Library/LaunchAgents/org.laeser.app.plist`
   (re-bootstrap cleanly if already loaded).
6. Print next steps (`laeserctl start`).

## Component 4: `deploy/laeserctl`

A small shell wrapper over `launchctl` so the user does not memorize its
syntax.

| Command | Action |
|---|---|
| `laeserctl start` | `launchctl kickstart gui/$UID/org.laeser.app` |
| `laeserctl stop` | `launchctl kill SIGTERM gui/$UID/org.laeser.app` |
| `laeserctl restart` | stop, then start |
| `laeserctl status` | `launchctl print gui/$UID/org.laeser.app` |
| `laeserctl logs` | `tail -f ~/Library/Logs/laeser/laeser.log` |

## Operational notes

- **Do not run the dev instance and the service simultaneously.** The dev
  command (`uvicorn --reload` on `:8000`) and the service (`:8473`) use
  different ports, but both open the same `laeser.db` and `library/`, running
  two schedulers and two download workers against shared state. Run one or the
  other.

## Repo changes

- New directory `deploy/` containing:
  - `org.laeser.app.plist.template`
  - `install.sh`
  - `laeserctl`
- `README.md` — add a "Running as a service" section alongside the existing
  dev command.
- No changes to any `.py` file.

## Security posture

Unchanged from today. The app has no authentication, but it binds `127.0.0.1`
only, so nothing off this machine can reach it. Plain HTTP is acceptable
because traffic never leaves the loopback interface. Going remote in the
future would make authentication and TLS mandatory — explicitly out of scope.

## Verification

Config/infra work; verification is manual:

1. `dscacheutil -q host -a name app.laeser.org` → resolves to `127.0.0.1`.
2. `laeserctl start`, then `curl -sI http://app.laeser.org:8473` → `200`.
3. Kill the uvicorn PID → it reappears within seconds (crash-restart).
4. `laeserctl stop` → process gone and stays gone (clean stop, no restart).
5. Close the terminal → app still reachable.
6. `README.md` documents the service workflow.
