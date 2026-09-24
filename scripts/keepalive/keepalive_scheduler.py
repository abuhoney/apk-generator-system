#!/usr/bin/env python3
"""
keepalive_scheduler.py
======================
Pure-Python scheduler that runs the keep-alive ping every 10 minutes.
This is the LOCAL FALLBACK for environments where cron-job.org is not
yet configured or where crontab is unavailable.

The scheduler uses the standard library `sched` module — no external
dependencies. It survives shell disconnects when run with setsid.

Usage:
    # Start as a long-running daemon
    setsid python3 /home/z/my-project/scripts/keepalive_scheduler.py \\
        > /home/z/my-project/logs/scheduler.log 2>&1 < /dev/null & disown

    # Or run in foreground (for debugging)
    python /home/z/my-project/scripts/keepalive_scheduler.py

cron-job.org is still RECOMMENDED as the primary mechanism because it
runs externally (independent of this container's lifetime). This local
scheduler is a safety net.
"""
from __future__ import annotations

import os
import sys
import time
import sched
import json
import subprocess
from datetime import datetime
from pathlib import Path

PING_INTERVAL_SEC = 600  # 10 minutes
KEEPALIVE_SCRIPT = Path("/home/z/my-project/scripts/render_keepalive_ping.py")
LOG_FILE = Path("/home/z/my-project/logs/keepalive_scheduler.log")
PID_FILE = Path("/home/z/my-project/logs/keepalive_scheduler.pid")
PYTHON_BIN = sys.executable

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def write_pid() -> None:
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception as e:
        log(f"Failed to write PID: {e}", "WARN")


def remove_pid() -> None:
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def is_already_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        return False


def run_ping(sc: sched.scheduler) -> None:
    """Execute one ping cycle and schedule the next one."""
    try:
        # Call the keepalive script in --once mode (state is tracked there)
        result = subprocess.run(
            [PYTHON_BIN, str(KEEPALIVE_SCRIPT), "--once"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            # Parse the last line of stdout for the summary
            last_line = (result.stdout or "").strip().splitlines()[-1] if result.stdout else ""
            log(f"Ping OK | {last_line}")
        else:
            log(f"Ping FAILED (exit {result.returncode}) | stderr: {result.stderr[:200]}", "ERROR")
    except subprocess.TimeoutExpired:
        log("Ping timed out after 120s — Render may be cold-starting", "WARN")
    except Exception as e:
        log(f"Ping exception: {type(e).__name__}: {e}", "ERROR")

    # Schedule next ping
    sc.enter(PING_INTERVAL_SEC, 1, run_ping, (sc,))


def main():
    if is_already_running():
        log("Another scheduler instance is already running. Exiting.", "WARN")
        sys.exit(1)

    write_pid()
    log("=" * 70)
    log("Universal APK Factory — Keep-Alive Scheduler (Local Fallback)")
    log(f"Backend:        https://html-to-apk-1789777001.onrender.com")
    log(f"Ping interval:  {PING_INTERVAL_SEC}s ({PING_INTERVAL_SEC // 60} min)")
    log(f"PID:            {os.getpid()}")
    log(f"Python:         {PYTHON_BIN}")
    log(f"Log file:       {LOG_FILE}")
    log("=" * 70)
    log("NOTE: For production reliability, also configure cron-job.org")
    log("      to ping https://html-to-apk-1789777001.onrender.com/api/app-types")
    log("      every 10 minutes (external, independent of this container).")
    log("=" * 70)

    # First ping immediately
    sc = sched.scheduler(time.time, time.sleep)
    sc.enter(0, 1, run_ping, (sc,))

    try:
        sc.run()
    except KeyboardInterrupt:
        log("Received SIGINT — shutting down")
    except Exception as e:
        log(f"Scheduler fatal error: {e}", "ERROR")
    finally:
        remove_pid()
        log("Scheduler stopped. PID file removed.")


if __name__ == "__main__":
    main()
