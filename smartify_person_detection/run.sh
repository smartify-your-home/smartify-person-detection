#!/bin/sh
set -u
echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Starte Add-on ..."

while true; do
    python3 /app/app.py
    echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Prozess beendet, starte in 3s neu ..."
    sleep 3
done
