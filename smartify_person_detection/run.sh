#!/bin/sh
set -u

# Prevent silently writing snapshots into the disposable container layer when
# the Supervisor did not attach the homeassistant_config volume.
python3 - <<'PY'
import os
import sys

root = "/homeassistant"
try:
    mount_lines = open("/proc/self/mountinfo", encoding="utf-8").read().splitlines()
except OSError as exc:
    print(f"FEHLER: Mountinformationen nicht lesbar: {exc}", flush=True)
    sys.exit(1)

matches = [
    line for line in mount_lines
    if len(line.split()) > 4 and line.split()[4] == root
]
for line in matches:
    print(f"Home-Assistant-Mount: {line}", flush=True)

if not matches or not os.path.ismount(root):
    print(
        "FEHLER: /homeassistant ist kein eigenes Mount! "
        "homeassistant_config fehlt im laufenden Add-on-Container. "
        "Stoppe zum Schutz der Snapshot-Daten. "
        "Bitte App im Home Assistant App Store aktualisieren und Container neu erstellen.",
        flush=True,
    )
    sys.exit(1)

if not os.access(root, os.W_OK):
    print("FEHLER: /homeassistant ist nicht beschreibbar.", flush=True)
    sys.exit(1)

print(f"Home-Assistant-Mount OK: /homeassistant device={os.stat(root).st_dev}", flush=True)
PY
if [ "$?" -ne 0 ]; then
    exit 1
fi

GALLERY_SRC="/app/slideshow_persondetection.html"
GALLERY_DST="/homeassistant/www/slideshow_persondetection.html"
GALLERY_CONFIG="/homeassistant/www/slideshow_persondetection_config.json"

if [ -f "$GALLERY_SRC" ]; then
    mkdir -p /homeassistant/www
    cp -f "$GALLERY_SRC" "$GALLERY_DST"

    python3 - <<'PY'
import json
from pathlib import Path

options_path = Path("/data/options.json")
config_path = Path("/homeassistant/www/slideshow_persondetection_config.json")

try:
    options = json.loads(options_path.read_text(encoding="utf-8"))
except Exception:
    options = {}

image_dir = str(
    options.get("image_dir", "/homeassistant/www/cam_pt2_motion")
).strip().rstrip("/")

try:
    image_count = int(options.get("rtsp_max_files", 100))
except Exception:
    image_count = 100

image_count = max(1, min(100, image_count))

www_root = "/homeassistant/www"
if image_dir == www_root:
    image_base_path = "/local/"
    error = ""
elif image_dir.startswith(www_root + "/"):
    rel = image_dir[len(www_root):].strip("/")
    image_base_path = f"/local/{rel}/"
    error = ""
else:
    image_base_path = ""
    error = (
        "Der konfigurierte image_dir liegt nicht unter /homeassistant/www "
        "und ist deshalb nicht über /local/ erreichbar."
    )

config_path.write_text(
    json.dumps(
        {
            "image_base_path": image_base_path,
            "image_count": image_count,
            "error": error,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
PY

    echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Slideshow installiert: /local/slideshow_persondetection.html"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Starte Add-on ..."

while true; do
    python3 /app/app.py
    echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] [Smartify Person Detection] Prozess beendet, starte in 3s neu ..."
    sleep 3
done
