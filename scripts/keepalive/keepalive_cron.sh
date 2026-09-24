#!/bin/bash
# Keep-alive ping for Render backend (called every 10 min)
# Prevents free-tier hibernation that causes 30s+ cold starts
PYTHON_BIN=/home/z/.venv/bin/python3
SCRIPT=/home/z/my-project/scripts/render_keepalive_ping.py
$PYTHON_BIN $SCRIPT --once
