#!/bin/sh
set -u

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
