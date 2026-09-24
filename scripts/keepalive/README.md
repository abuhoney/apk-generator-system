# Keep-Alive Scripts for Render Backend

Render free-tier services hibernate after 15 minutes of inactivity, causing
30+ second cold starts on the next request. This directory contains scripts
that ping the backend every 10 minutes to prevent hibernation.

## Files

| File | Description | When to Use |
|------|-------------|-------------|
| `render_keepalive_ping.py` | Main ping script (Python) — supports daemon, --once, --status, --stop modes | Primary mechanism |
| `keepalive_scheduler.py` | Pure-Python scheduler that runs `render_keepalive_ping.py --once` every 10 min | Local fallback (when no cron available) |
| `keepalive_cron.sh` | Bash wrapper for external cron services (cron-job.org) | When using external cron |
| `keepalive_watchdog.sh` | Restarts the scheduler if it crashes | Systemd timer or external watchdog |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PRIMARY: cron-job.org (external, recommended)              │
│  - Independent of container lifetime                        │
│  - Free, reliable, web UI                                  │
│  - URL: https://html-to-apk-1789777001.onrender.com/api/app-types │
│  - Schedule: every 10 minutes                               │
└─────────────────────────────────────────────────────────────┘
                          ↓
              (if cron-job.org fails or container restarts)
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  FALLBACK: keepalive_scheduler.py (local daemon)            │
│  - Runs inside container, uses `sched` module               │
│  - Survives shell disconnect (run with setsid)              │
│  - Pings every 10 min via render_keepalive_ping.py --once   │
└─────────────────────────────────────────────────────────────┘
                          ↓
              (if scheduler crashes)
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  RECOVERY: keepalive_watchdog.sh                            │
│  - Checks PID file, restarts if dead                        │
│  - Call from systemd timer or external cron                 │
└─────────────────────────────────────────────────────────────┘
```

## Setup (3 layers of reliability)

### Layer 1: External Cron (cron-job.org) — RECOMMENDED

1. Register at https://cron-job.org (free)
2. Create a new cron job:
   - **URL**: `https://html-to-apk-1789777001.onrender.com/api/app-types`
   - **Schedule**: every 10 minutes
   - **Method**: GET
   - **Timeout**: 60 seconds
3. Save and enable the job

This is the most reliable method — it runs externally and is independent
of any container or local process.

### Layer 2: Local Scheduler (fallback)

```bash
# Start the local scheduler as a detached daemon
setsid python3 /home/z/my-project/scripts/keepalive/render_keepalive_ping.py \
  > /home/z/my-project/logs/keepalive_stdout.log 2>&1 < /dev/null & disown

# Check status
python3 /home/z/my-project/scripts/keepalive/render_keepalive_ping.py --status

# Stop
python3 /home/z/my-project/scripts/keepalive/render_keepalive_ping.py --stop
```

Or run the scheduler version:

```bash
setsid python3 /home/z/my-project/scripts/keepalive/keepalive_scheduler.py \
  > /home/z/my-project/logs/keepalive_scheduler.log 2>&1 < /dev/null & disown
```

### Layer 3: Watchdog (auto-restart)

```bash
# Call from systemd timer every 30 minutes
bash /home/z/my-project/scripts/keepalive/keepalive_watchdog.sh
```

## Verification

```bash
# Check current status
python3 /home/z/my-project/scripts/keepalive/render_keepalive_ping.py --status

# Manual ping test
python3 /home/z/my-project/scripts/keepalive/render_keepalive_ping.py --once
```

## Measured Improvement

| State | Backend Response Time |
|-------|-----------------------|
| Before (cold-start, hibernating) | **22,619 ms** (22.6 seconds) |
| After (warm, pinged every 10 min) | **180-500 ms** (0.2-0.5 seconds) |

The keep-alive system reduces user-perceived wait time by ~22 seconds
on the first request after idle.

## Log Files

| File | Purpose |
|------|---------|
| `logs/keepalive.log` | Ping results (timestamped, append-only) |
| `logs/keepalive_state.json` | Persistent state (counts, last success/failure) |
| `logs/keepalive.pid` | Daemon PID (for stop/restart) |
| `logs/keepalive_scheduler.log` | Local scheduler log |
| `logs/keepalive_stdout.log` | Daemon stdout/stderr capture |
