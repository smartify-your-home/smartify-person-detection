#!/bin/sh
set -u

GALLERY_SRC="/app/slideshow_persondetection.html"
GALLERY_DST="/homeassistant/www/slideshow_persondetection.html"

if [ -f "$GALLERY_SRC" ]; then
    mkdir -p /homeassistant/www
    cp -f "$GALLERY_SRC" "$GALLERY_DST"
    echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Slideshow installiert: /local/slideshow_persondetection.html"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Starte Add-on ..."

while true; do
    python3 /app/app.py
    echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Prozess beendet, starte in 3s neu ..."
    sleep 3
done
