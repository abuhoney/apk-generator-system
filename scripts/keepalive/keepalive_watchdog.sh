#!/bin/bash
# Watchdog: ensures render_keepalive_ping.py is running, restarts if dead
# Call this from cron or systemd timer

PID_FILE=/home/z/my-project/logs/keepalive.pid
PYTHON_BIN=/home/z/.venv/bin/python3
DAEMON=/home/z/my-project/scripts/render_keepalive_ping.py
LOG=/home/z/my-project/logs/keepalive_stdout.log

# Check if daemon is alive
ALIVE=0
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        ALIVE=1
    fi
fi

if [ "$ALIVE" -eq 0 ]; then
    echo "[$(date)] Daemon not running — restarting..." >> "$LOG"
    rm -f "$PID_FILE"
    setsid $PYTHON_BIN "$DAEMON" >> "$LOG" 2>&1 < /dev/null &
    disown
    sleep 2
    if [ -f "$PID_FILE" ]; then
        NEW_PID=$(cat "$PID_FILE")
        echo "[$(date)] Daemon restarted with PID $NEW_PID" >> "$LOG"
    else
        echo "[$(date)] ERROR: Daemon failed to start" >> "$LOG"
    fi
else
    echo "[$(date)] Daemon alive (PID $(cat $PID_FILE))" >> "$LOG"
fi
