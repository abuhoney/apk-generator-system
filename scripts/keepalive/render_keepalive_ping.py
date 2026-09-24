#!/usr/bin/env python3
"""
render_keepalive_ping.py
========================
Pings the Universal APK Factory backend on Render every 10 minutes
to prevent free-tier hibernation (which causes 30s+ cold starts).

Render free-tier services hibernate after 15 minutes of inactivity.
A single GET request to /api/app-types is enough to reset the timer.

Usage:
    # Run as a daemon (foreground, logs to stdout)
    python /home/z/my-project/scripts/render_keepalive_ping.py

    # Or as a background service via nohup
    nohup python /home/z/my-project/scripts/render_keepalive_ping.py \\
        > /home/z/my-project/logs/keepalive.log 2>&1 &

    # Or run once (cron mode)
    python /home/z/my-project/scripts/render_keepalive_ping.py --once
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════

BACKEND_URL = "https://html-to-apk-1789777001.onrender.com"
PING_INTERVAL_SEC = 600  # 10 minutes (Render hibernates after 15 min)
HEALTH_ENDPOINT = "/api/app-types"
LOG_DIR = Path("/home/z/my-project/logs")
LOG_FILE = LOG_DIR / "keepalive.log"
PID_FILE = LOG_DIR / "keepalive.pid"
STATE_FILE = LOG_DIR / "keepalive_state.json"

# Ensure log directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════

def log(message: str, level: str = "INFO") -> None:
    """Log a message with timestamp to both stdout and the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # Don't fail the daemon if logging fails


# ═══════════════════════════════════════════════════════════════════════════
# State Tracking
# ═══════════════════════════════════════════════════════════════════════════

def load_state() -> dict:
    """Load the persisted ping state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {
        "total_pings": 0,
        "successful_pings": 0,
        "failed_pings": 0,
        "last_ping_time": None,
        "last_success_time": None,
        "last_failure_time": None,
        "last_status_code": None,
        "last_latency_ms": None,
        "started_at": datetime.now().isoformat(),
    }


def save_state(state: dict) -> None:
    """Persist the ping state to disk."""
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"Failed to save state: {e}", "WARN")


# ═══════════════════════════════════════════════════════════════════════════
# Ping Logic
# ═══════════════════════════════════════════════════════════════════════════

def ping_backend() -> dict:
    """Send a single GET request to the Render backend health endpoint.

    Returns a dict with:
        - success: bool
        - status_code: int or None
        - latency_ms: int
        - error: str or None
        - app_types_count: int or None
    """
    url = f"{BACKEND_URL}{HEALTH_ENDPOINT}"
    t0 = time.time()

    try:
        req = urllib.request.Request(url, method="GET", headers={
            "User-Agent": "UniversalAPKFactory-KeepAlive/1.0"
        })
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", errors="replace")
            latency_ms = int((time.time() - t0) * 1000)

            # Parse app types count for additional verification
            app_types_count = None
            try:
                data = json.loads(body)
                if isinstance(data, dict) and "types" in data:
                    app_types_count = len(data["types"])
                elif isinstance(data, list):
                    app_types_count = len(data)
            except Exception:
                pass

            return {
                "success": True,
                "status_code": r.status,
                "latency_ms": latency_ms,
                "error": None,
                "app_types_count": app_types_count,
            }
    except urllib.error.HTTPError as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "status_code": e.code,
            "latency_ms": latency_ms,
            "error": f"HTTP {e.code}: {e.reason}",
            "app_types_count": None,
        }
    except urllib.error.URLError as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": f"URLError: {e.reason}",
            "app_types_count": None,
        }
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "status_code": None,
            "latency_ms": latency_ms,
            "error": f"{type(e).__name__}: {e}",
            "app_types_count": None,
        }


def run_ping_cycle(state: dict) -> dict:
    """Run one ping cycle and update state."""
    result = ping_backend()
    state["total_pings"] += 1
    state["last_ping_time"] = datetime.now().isoformat()
    state["last_status_code"] = result["status_code"]
    state["last_latency_ms"] = result["latency_ms"]

    if result["success"]:
        state["successful_pings"] += 1
        state["last_success_time"] = datetime.now().isoformat()
        log(f"PING OK | HTTP {result['status_code']} | {result['latency_ms']}ms | "
            f"{result['app_types_count']} app types available")
    else:
        state["failed_pings"] += 1
        state["last_failure_time"] = datetime.now().isoformat()
        log(f"PING FAIL | {result['error']} | {result['latency_ms']}ms", "ERROR")

    save_state(state)
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Daemon Mode
# ═══════════════════════════════════════════════════════════════════════════

def write_pid() -> None:
    """Write the current process PID to the PID file."""
    try:
        PID_FILE.write_text(str(os.getpid()))
    except Exception as e:
        log(f"Failed to write PID file: {e}", "WARN")


def remove_pid() -> None:
    """Remove the PID file on exit."""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def is_already_running() -> bool:
    """Check if another instance is already running."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if the process is still alive
        try:
            os.kill(pid, 0)  # Signal 0 = check existence
            return True
        except OSError:
            # Process is dead; clean up stale PID
            PID_FILE.unlink()
            return False
    except Exception:
        return False


def daemon_loop() -> None:
    """Run the keep-alive daemon forever (every 10 minutes)."""
    if is_already_running():
        log("Another keep-alive instance is already running. Exiting.", "WARN")
        sys.exit(1)

    write_pid()
    log("=" * 70)
    log(f"Universal APK Factory — Render Keep-Alive Daemon Started")
    log(f"Backend:      {BACKEND_URL}")
    log(f"Ping every:   {PING_INTERVAL_SEC}s ({PING_INTERVAL_SEC // 60} minutes)")
    log(f"PID:          {os.getpid()}")
    log(f"Log file:     {LOG_FILE}")
    log(f"State file:   {STATE_FILE}")
    log("=" * 70)

    state = load_state()
    log(f"Resuming from state: {state['total_pings']} total pings, "
        f"{state['successful_pings']} OK, {state['failed_pings']} failed")

    # First ping immediately (in case backend is hibernating)
    log("Sending initial ping to wake backend if hibernating...")
    run_ping_cycle(state)

    # Then loop forever
    try:
        cycle = 1
        while True:
            log(f"[cycle {cycle}] Sleeping {PING_INTERVAL_SEC}s until next ping...")
            time.sleep(PING_INTERVAL_SEC)
            run_ping_cycle(state)
            cycle += 1
    except KeyboardInterrupt:
        log("Received SIGINT — shutting down gracefully")
    except Exception as e:
        log(f"Unexpected error in main loop: {e}", "ERROR")
    finally:
        remove_pid()
        log("Daemon stopped. PID file removed.")


# ═══════════════════════════════════════════════════════════════════════════
# Status & Control Commands
# ═══════════════════════════════════════════════════════════════════════════

def show_status() -> None:
    """Print the current ping daemon status."""
    if not STATE_FILE.exists():
        print("No state file found — daemon has never run.")
        return

    state = json.loads(STATE_FILE.read_text())

    print("=" * 60)
    print("  Universal APK Factory — Keep-Alive Daemon Status")
    print("=" * 60)
    print(f"  Started at:        {state.get('started_at', 'unknown')}")
    print(f"  Total pings:       {state.get('total_pings', 0)}")
    print(f"  Successful:        {state.get('successful_pings', 0)}")
    print(f"  Failed:            {state.get('failed_pings', 0)}")
    success_rate = (state.get('successful_pings', 0) / max(state.get('total_pings', 1), 1)) * 100
    print(f"  Success rate:      {success_rate:.1f}%")
    print(f"  Last ping:         {state.get('last_ping_time', 'never')}")
    print(f"  Last success:      {state.get('last_success_time', 'never')}")
    print(f"  Last failure:      {state.get('last_failure_time', 'never')}")
    print(f"  Last status code:  {state.get('last_status_code', '-')}")
    print(f"  Last latency:      {state.get('last_latency_ms', '-')} ms")
    print("=" * 60)

    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        print(f"  Daemon PID:        {pid}")
        try:
            os.kill(int(pid), 0)
            print(f"  Daemon status:     RUNNING")
        except OSError:
            print(f"  Daemon status:     STOPPED (stale PID)")
    else:
        print(f"  Daemon status:     NOT RUNNING")
    print("=" * 60)


def stop_daemon() -> None:
    """Stop the running daemon if any."""
    if not PID_FILE.exists():
        print("Daemon is not running (no PID file).")
        return
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 15)  # SIGTERM
        print(f"Sent SIGTERM to daemon (PID {pid}). Waiting for graceful shutdown...")
        time.sleep(2)
        try:
            os.kill(pid, 0)
            print(f"Daemon still alive — sending SIGKILL")
            os.kill(pid, 9)
        except OSError:
            pass
        remove_pid()
        print("Daemon stopped.")
    except Exception as e:
        print(f"Error stopping daemon: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global PING_INTERVAL_SEC

    parser = argparse.ArgumentParser(
        description="Universal APK Factory — Render Keep-Alive Daemon"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single ping and exit (cron mode)"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show current daemon status and exit"
    )
    parser.add_argument(
        "--stop", action="store_true",
        help="Stop the running daemon"
    )
    parser.add_argument(
        "--interval", type=int, default=PING_INTERVAL_SEC,
        help=f"Ping interval in seconds (default: {PING_INTERVAL_SEC})"
    )
    args = parser.parse_args()

    if args.status:
        show_status()
        return
    if args.stop:
        stop_daemon()
        return

    # Override interval if provided
    if args.interval != PING_INTERVAL_SEC:
        PING_INTERVAL_SEC = args.interval
        log(f"Ping interval overridden to {PING_INTERVAL_SEC}s")

    if args.once:
        # Single ping mode (for cron)
        state = load_state()
        result = run_ping_cycle(state)
        sys.exit(0 if result["success"] else 1)

    # Daemon mode (default)
    daemon_loop()


if __name__ == "__main__":
    main()
