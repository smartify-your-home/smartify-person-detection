import json
import hashlib
import re
import os
import sys
import shutil
import time
import threading

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, quote, parse_qs
from urllib.request import Request, urlopen

from pathlib import Path
from datetime import datetime, timezone

# Jede App-Protokollmeldung mit lokaler Uhrzeit versehen. Der Wrapper greift
# auch für Meldungen aus MQTT-, Kamera- und Webserver-Threads.
import builtins

_ORIGINAL_PRINT = builtins.print
_LOG_PRINT_LOCK = threading.RLock()

def _timestamped_print(*args, **kwargs):
    if kwargs.get("file", sys.stdout) not in (None, sys.stdout):
        return _ORIGINAL_PRINT(*args, **kwargs)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    with _LOG_PRINT_LOCK:
        kwargs.setdefault("flush", True)
        return _ORIGINAL_PRINT(f"[{timestamp}]", *args, **kwargs)

builtins.print = _timestamped_print

import cv2
import numpy as np
import onnxruntime as ort
import paho.mqtt.client as mqtt


# ---------------------------------------------------------
# Home Assistant Add-on Optionen
# ---------------------------------------------------------

OPTIONS_FILE = Path("/data/options.json")
STATE = Path("/data/state.json")

O = json.loads(OPTIONS_FILE.read_text())


def g(key, default):
    return O.get(key, default)


IMG = Path(g("image_dir", "/homeassistant/www/cam_pt2_motion"))

HOST = g("mqtt_host", "core-mosquitto")
PORT = int(g("mqtt_port", 1883))

USER = g("mqtt_username", "")
PW = g("mqtt_password", "")

PREFIX = g("mqtt_topic_prefix", "smartify_person_detection")
DISC = g("mqtt_discovery_prefix", "homeassistant")

BATCH_SIZE = int(g("batch_size", 3))
TH = float(g("yellow_ratio_threshold", 0.18))
CONF = float(g("person_confidence", 0.45))
# YOLO mit niedriger Kandidaten-Schwelle laufen lassen. Die konfigurierte
# CONF bleibt die normale Mindest-Confidence; nur bei deutlich starkem
# Gelbanteil darf ein Kandidat mit niedrigerer Confidence als Postbote gelten.
CONF_SCAN = min(CONF, 0.25)
STRONG_YELLOW_FACTOR = 1.5

SCAN_INTERVAL = max(0.5, float(g("scan_interval_seconds", 2)))
PARTIAL_BATCH_TIMEOUT_SECONDS = max(5.0, float(g("partial_batch_timeout_seconds", 60)))
RTSP_FALLBACK_AFTER_SECONDS = max(5.0, float(g("rtsp_fallback_after_seconds", 15)))
PERSON_ON_SECONDS = int(g("person_sensor_on_seconds", 60))
POST_AUTO_RESET = bool(g("post_auto_reset", False))
PERSON_AUTO_RESET = bool(g("person_auto_reset", False))

ONSECS = int(g("binary_sensor_on_seconds", 14000))
RESET_BINARIES_AT_MIDNIGHT = bool(g("reset_binaries_at_midnight", False))
POST_ENTITY_ID = str(g("post_entity_id", "binary_sensor.smartify_person_detection_post")).strip() or "binary_sensor.smartify_person_detection_post"
PERSON_ENTITY_ID = str(g("person_entity_id", "binary_sensor.smartify_person_detection_person")).strip() or "binary_sensor.smartify_person_detection_person"

# Optionaler Erkennungston über einen Home-Assistant-Mediaplayer.
# Ein Postboten-Treffer ist zugleich eine Person; pro Event wird deshalb
# nur EIN Ton abgespielt, wobei Post Vorrang vor Person hat.
SOUND_ENABLED = bool(g("sound_enabled", False))
SOUND_MEDIA_PLAYER = str(g("sound_media_player", "")).strip()
PERSON_SOUND = str(g("person_sound", "")).strip()
POST_SOUND = str(g("post_sound", "")).strip()
SOUND_BASE_URL = str(g("sound_base_url", "")).strip().rstrip("/")
SOUND_MEDIA_CONTENT_TYPE = str(g("sound_media_content_type", "music")).strip() or "music"

# Haustuer-Erkennung
DOOR_ENABLED = bool(g("door_enabled", True))
DOOR_CAMERA_ENTITY = str(g("door_camera_entity", "camera.cam_pt2_mainstream"))
DOOR_CHECK_INTERVAL = max(5, int(g("door_check_interval_seconds", 60)))
DOOR_PAUSE_AFTER_MOTION = max(0, int(g("door_pause_after_motion_seconds", 20)))
DOOR_OPEN_SHIFT_PX = max(0.5, float(g("door_open_shift_pixels", 3.0)))
DOOR_CLOSE_SHIFT_PX = max(0.0, float(g("door_close_shift_pixels", 1.5)))
DOOR_CALIBRATION_UI_MINUTES = max(1, int(g("door_calibration_ui_minutes", 15)))
DOOR_CALIBRATION_UI_SECONDS = DOOR_CALIBRATION_UI_MINUTES * 60
DOOR_EDGE_TRACK_WINDOW_PX = max(1.0, float(g("door_edge_track_window_pixels", 4.0)))
DOOR_EDGE_MIN_QUALITY = max(1.0, float(g("door_edge_min_quality", 1.20)))
DOOR_EDGE_MIN_TEMPLATE_CORR = min(0.99, max(-1.0, float(g("door_edge_min_template_corr", 0.45))))
DOOR_WEB_PORT = 8099
INGRESS_ALLOWED_IP = "172.30.32.2"
DOOR_REFERENCE = Path("/data/door_reference.jpg")
DOOR_EDGE_REFERENCE = Path("/data/door_edge_reference_v4.json")
DOOR_CONFIG = Path("/data/door_config.json")

# Optionale zweite, vertikale Abstandsmessung (z. B. Garagentor)
VERTICAL_ENABLED = bool(g("vertical_enabled", False))
VERTICAL_NAME = str(g("vertical_name", "Garagentor")).strip() or "Garagentor"
VERTICAL_ENTITY_ID = str(g("vertical_entity_id", "binary_sensor.garagentor")).strip() or "binary_sensor.garagentor"
DOOR_NAME = str(g("door_name", "Haustür")).strip() or "Haustür"
DOOR_ENTITY_ID = str(g("door_entity_id", "binary_sensor.haustuer")).strip() or "binary_sensor.haustuer"
VERTICAL_OPEN_SHIFT_PX = max(0.5, float(g("vertical_open_shift_pixels", 3.0)))
VERTICAL_CLOSE_SHIFT_PX = max(0.0, float(g("vertical_close_shift_pixels", 1.5)))
VERTICAL_REFERENCE = Path("/data/vertical_reference.jpg")
VERTICAL_EDGE_REFERENCE = Path("/data/vertical_edge_reference_v2.json")
VERTICAL_CONFIG = Path("/data/vertical_config.json")

# Optionale dritte Messung: zweites Garagentor
VERTICAL2_ENABLED = bool(g("vertical2_enabled", False))
VERTICAL2_NAME = str(g("vertical2_name", "Garagentor 2")).strip() or "Garagentor 2"
VERTICAL2_ENTITY_ID = str(g("vertical2_entity_id", "binary_sensor.garagentor_2")).strip() or "binary_sensor.garagentor_2"
VERTICAL2_OPEN_SHIFT_PX = max(0.5, float(g("vertical2_open_shift_pixels", 3.0)))
VERTICAL2_CLOSE_SHIFT_PX = max(0.0, float(g("vertical2_close_shift_pixels", 1.5)))
VERTICAL2_REFERENCE = Path("/data/vertical2_reference.jpg")
VERTICAL2_EDGE_REFERENCE = Path("/data/vertical2_edge_reference_v1.json")
VERTICAL2_CONFIG = Path("/data/vertical2_config.json")
ENTITY_IDENTITY_STATE = Path("/data/entity_identity.json")
PERSON_ROI_CONFIG = Path("/data/person_roi.json")
SNAPSHOT_DIR = Path(g("snapshot_dir", "/homeassistant/www/smartify_person_detection"))
SNAPSHOT_FILENAME = "post_latest.jpg"
SNAPSHOT_PATH = SNAPSHOT_DIR / SNAPSHOT_FILENAME
PERSON_SNAPSHOT_FILENAME = "person_latest.jpg"
PERSON_SNAPSHOT_PATH = SNAPSHOT_DIR / PERSON_SNAPSHOT_FILENAME
try:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
except Exception as exc:
    print(f"Warnung: Snapshot-Ordner konnte nicht angelegt werden: {exc}")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")


_HA_BASE_URL_CACHE = None
_HA_BASE_URL_LOCK = threading.Lock()


def _ha_api_request(path, payload=None, timeout=10):
    if not SUPERVISOR_TOKEN:
        raise RuntimeError(
            "SUPERVISOR_TOKEN fehlt. homeassistant_api muss aktiviert sein."
        )

    data = None
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Accept": "application/json",
    }

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(
        f"http://supervisor/core/api{path}",
        data=data,
        headers=headers,
        method="POST" if payload is not None else "GET",
    )

    with urlopen(req, timeout=timeout) as response:
        raw = response.read()

    if not raw:
        return None

    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _homeassistant_base_url():
    """LAN-taugliche HA-Basis-URL für /local/-Sounds bestimmen."""
    global _HA_BASE_URL_CACHE

    if SOUND_BASE_URL:
        return SOUND_BASE_URL

    with _HA_BASE_URL_LOCK:
        if _HA_BASE_URL_CACHE is not None:
            return _HA_BASE_URL_CACHE

        base = ""
        try:
            cfg = _ha_api_request("/config", timeout=5)
            if isinstance(cfg, dict):
                base = str(
                    cfg.get("internal_url")
                    or cfg.get("external_url")
                    or ""
                ).strip().rstrip("/")
        except Exception as exc:
            print(f"Sound: Home-Assistant-URL konnte nicht automatisch ermittelt werden: {exc}")

        _HA_BASE_URL_CACHE = base
        return base


def _resolve_sound_content_id(value):
    value = str(value or "").strip()
    if not value:
        return ""

    # /local/... ist für Browser relativ. Viele physische Mediaplayer
    # benötigen eine absolute URL; dafür wird bevorzugt HA internal_url genutzt.
    if value.startswith("/local/"):
        base = _homeassistant_base_url()
        if base:
            return base + value

    return value


def play_detection_sound(kind):
    """Genau einen konfigurierten Ton für 'person' oder 'post' abspielen."""
    if not SOUND_ENABLED:
        return

    if not SOUND_MEDIA_PLAYER:
        print("Sound: aktiviert, aber kein Mediaplayer konfiguriert.")
        return

    if not SOUND_MEDIA_PLAYER.startswith("media_player."):
        print(f"Sound: ungültige Mediaplayer-Entity: {SOUND_MEDIA_PLAYER}")
        return

    raw_sound = POST_SOUND if kind == "post" else PERSON_SOUND
    sound = _resolve_sound_content_id(raw_sound)

    if not sound:
        print(f"Sound: für {kind} ist kein Ton konfiguriert.")
        return

    payload = {
        "entity_id": SOUND_MEDIA_PLAYER,
        "media_content_id": sound,
        "media_content_type": SOUND_MEDIA_CONTENT_TYPE,
    }

    try:
        _ha_api_request(
            "/services/media_player/play_media",
            payload=payload,
            timeout=10,
        )
        print(
            f"Sound: {kind} über {SOUND_MEDIA_PLAYER} abgespielt: {sound}"
        )
    except Exception as exc:
        print(
            f"Sound: Wiedergabe für {kind} über {SOUND_MEDIA_PLAYER} fehlgeschlagen: "
            f"{type(exc).__name__}: {exc}"
        )


# ---------------------------------------------------------
# MQTT Topics
# ---------------------------------------------------------

status = f"{PREFIX}/status"
person_status = f"{PREFIX}/person_status"

avail = f"{PREFIX}/availability"

last = f"{PREFIX}/last_detection"
image_topic = f"{PREFIX}/image"
ratio_topic = f"{PREFIX}/yellow_ratio"

person_image_topic = f"{PREFIX}/person_image"

post_attributes_topic = f"{PREFIX}/post_attributes"
person_attributes_topic = f"{PREFIX}/person_attributes"

door_status_topic = f"{PREFIX}/door/status"
door_attributes_topic = f"{PREFIX}/door/attributes"
vertical_status_topic = f"{PREFIX}/vertical/status"
vertical_attributes_topic = f"{PREFIX}/vertical/attributes"
vertical2_status_topic = f"{PREFIX}/vertical2/status"
vertical2_attributes_topic = f"{PREFIX}/vertical2/attributes"

RESET_TOPIC = f"{PREFIX}/reset"
POST_RESET_TOPIC = f"{PREFIX}/post_reset"


# ---------------------------------------------------------
# YOLO (ONNX Runtime statt Ultralytics/PyTorch)
# ---------------------------------------------------------

MODEL_PATH = "/app/yolo11n.onnx"
YOLO_IMGSZ = 640
YOLO_IOU = 0.7  # entspricht dem Ultralytics-Default

print("Lade YOLO11n (ONNX) ...")

_so = ort.SessionOptions()
_so.intra_op_num_threads = 2
_so.inter_op_num_threads = 1

session = ort.InferenceSession(
    MODEL_PATH,
    sess_options=_so,
    providers=["CPUExecutionProvider"]
)
_input_name = session.get_inputs()[0].name

print("YOLO geladen.")


def detect_persons(img, conf_min):
    """Personen (COCO-Klasse 0) erkennen.

    Rueckgabe: Liste von (x1, y1, x2, y2, conf) in Koordinaten von img,
    absteigend nach Confidence sortiert (wie bei Ultralytics).
    """
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        return []

    # Letterbox auf 640x640, Fuellfarbe 114 wie bei Ultralytics
    r = min(YOLO_IMGSZ / h, YOLO_IMGSZ / w)
    nw, nh = int(round(w * r)), int(round(h * r))
    top = int(round((YOLO_IMGSZ - nh) / 2 - 0.1))
    left = int(round((YOLO_IMGSZ - nw) / 2 - 0.1))

    canvas = np.full((YOLO_IMGSZ, YOLO_IMGSZ, 3), 114, dtype=np.uint8)
    canvas[top:top + nh, left:left + nw] = cv2.resize(
        img, (nw, nh), interpolation=cv2.INTER_LINEAR
    )
    blob = (
        cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
        .transpose(2, 0, 1)[None]
        .astype(np.float32) / 255.0
    )

    # Ausgabe (1, 84, 8400): cx, cy, w, h + 80 Klassen-Scores
    out = session.run(None, {_input_name: blob})[0][0]
    scores = out[4]
    keep = scores >= conf_min
    if not np.any(keep):
        return []

    cx, cy, bw, bh = out[0][keep], out[1][keep], out[2][keep], out[3][keep]
    sc = scores[keep]

    x1 = (cx - bw / 2.0 - left) / r
    y1 = (cy - bh / 2.0 - top) / r
    bw = bw / r
    bh = bh / r

    rects = [
        [float(a), float(b), float(c), float(d)]
        for a, b, c, d in zip(x1, y1, bw, bh)
    ]
    idx = cv2.dnn.NMSBoxes(rects, sc.tolist(), float(conf_min), YOLO_IOU)

    result = []
    for i in np.array(idx).flatten():
        bx, by, bww, bhh = rects[int(i)]
        bx1 = max(0, min(w, int(bx)))
        by1 = max(0, min(h, int(by)))
        bx2 = max(0, min(w, int(bx + bww)))
        by2 = max(0, min(h, int(by + bhh)))
        result.append((bx1, by1, bx2, by2, float(sc[int(i)])))

    result.sort(key=lambda t: t[4], reverse=True)
    return result


# ---------------------------------------------------------
# Verarbeitungsstatus
# ---------------------------------------------------------

def local_date_string():
    return datetime.now().astimezone().date().isoformat()


_state_rtsp_cleanup_needed = False
_state_rtsp_cleanup_count = 0


def load_state():
    global _state_rtsp_cleanup_needed, _state_rtsp_cleanup_count

    try:
        data = json.loads(STATE.read_text())

        processed_data = data.get("processed", {})
        if not isinstance(processed_data, dict):
            processed_data = {}

        # RTSP-Frames werden direkt von rtsp_source.py verarbeitet und gehören
        # nicht in den persistenten Ordner-Fallback-Status. Seit den
        # Zeitstempel-Dateinamen würde state.json sonst dauerhaft wachsen.
        rtsp_names = [
            name for name in processed_data
            if str(name).lower().startswith("rtsp_")
        ]
        if rtsp_names:
            _state_rtsp_cleanup_needed = True
            _state_rtsp_cleanup_count = len(rtsp_names)
            processed_data = {
                name: value
                for name, value in processed_data.items()
                if not str(name).lower().startswith("rtsp_")
            }

        counter_date_value = str(
            data.get(
                "counter_date",
                local_date_string()
            )
        )

        person_count_value = int(
            data.get(
                "person_count_today",
                0
            )
        )

        post_count_value = int(
            data.get(
                "post_count_today",
                0
            )
        )

        person_history_value = data.get("person_detection_history", [])
        if not isinstance(person_history_value, list):
            person_history_value = []
        person_history_value = [str(v) for v in person_history_value][-10:]

        post_history_value = data.get("post_detection_history", [])
        if not isinstance(post_history_value, list):
            post_history_value = []
        post_history_value = [str(v) for v in post_history_value][-10:]

        return (
            processed_data,
            counter_date_value,
            person_count_value,
            post_count_value,
            person_history_value,
            post_history_value
        )

    except Exception:
        return (
            {},
            local_date_string(),
            0,
            0,
            [],
            []
        )


(
    processed,
    counter_date,
    person_count_today,
    post_count_today,
    person_detection_history,
    post_detection_history
) = load_state()


state_lock = threading.Lock()


def save_state():
    with state_lock:
        STATE.write_text(
            json.dumps(
                {
                    "processed": processed,
                    "counter_date": counter_date,
                    "person_count_today": person_count_today,
                    "post_count_today": post_count_today,
                    "person_detection_history": person_detection_history[-10:],
                    "post_detection_history": post_detection_history[-10:]
                },
                indent=2
            )
        )


if _state_rtsp_cleanup_needed:
    save_state()
    print(
        f"State-Bereinigung: {_state_rtsp_cleanup_count} alte "
        "rtsp_* Eintraege aus /data/state.json entfernt."
    )


def _rect_to_rotated_roi(value, fallback):
    result = dict(fallback)
    if not isinstance(value, dict):
        return result

    # Neues Format: Mittelpunkt, Groesse, Winkel in Grad.
    if all(k in value for k in ("cx", "cy", "w", "h")):
        for key in ("cx", "cy", "w", "h", "angle"):
            try:
                result[key] = float(value.get(key, result[key]))
            except Exception:
                pass
        return result

    # Migration aus 1.2.4/1.2.5 (achsenparalleles Rechteck).
    if all(k in value for k in ("x1", "y1", "x2", "y2")):
        try:
            x1, y1 = float(value["x1"]), float(value["y1"])
            x2, y2 = float(value["x2"]), float(value["y2"])
            result.update({
                "cx": (x1 + x2) / 2.0,
                "cy": (y1 + y2) / 2.0,
                "w": max(0.005, x2 - x1),
                "h": max(0.005, y2 - y1),
                "angle": 0.0,
            })
        except Exception:
            pass
    return result


def _sanitize_rotated_roi(value, fallback):
    r = _rect_to_rotated_roi(value, fallback)
    r["w"] = min(max(float(r["w"]), 0.003), 0.95)
    r["h"] = min(max(float(r["h"]), 0.006), 0.95)
    r["cx"] = min(max(float(r["cx"]), 0.0), 1.0)
    r["cy"] = min(max(float(r["cy"]), 0.0), 1.0)
    r["angle"] = min(max(float(r.get("angle", 0.0)), -45.0), 45.0)
    return r


def load_door_config():
    default = {
        "fixed": {"cx": 0.714, "cy": 0.50, "w": 0.028, "h": 0.60, "angle": 0.0},
        "moving": {"cx": 0.746, "cy": 0.50, "w": 0.028, "h": 0.60, "angle": 0.0},
    }

    try:
        data = json.loads(DOOR_CONFIG.read_text())
        if isinstance(data.get("fixed"), dict) or isinstance(data.get("moving"), dict):
            default["fixed"] = _sanitize_rotated_roi(data.get("fixed"), default["fixed"])
            default["moving"] = _sanitize_rotated_roi(data.get("moving"), default["moving"])
            return default

        # Migration des alten einzelnen ROI in zwei Startbereiche.
        if all(k in data for k in ("x1", "y1", "x2", "y2")):
            x1, y1 = float(data["x1"]), float(data["y1"])
            x2, y2 = float(data["x2"]), float(data["y2"])
            mid = (x1 + x2) / 2.0
            pad = max(0.001, (x2 - x1) * 0.04)
            fixed = {"x1": x1, "y1": y1, "x2": max(x1 + 0.005, mid - pad), "y2": y2}
            moving = {"x1": min(x2 - 0.005, mid + pad), "y1": y1, "x2": x2, "y2": y2}
            default["fixed"] = _sanitize_rotated_roi(fixed, default["fixed"])
            default["moving"] = _sanitize_rotated_roi(moving, default["moving"])
    except Exception:
        pass

    return default


door_rois = load_door_config()
door_config_lock = threading.Lock()


def load_vertical_config():
    default={
      "fixed":{"cx":0.45,"cy":0.35,"w":0.55,"h":0.035,"angle":0.0},
      "moving":{"cx":0.45,"cy":0.55,"w":0.55,"h":0.035,"angle":0.0},
    }
    try:
        data=json.loads(VERTICAL_CONFIG.read_text())
        for n in ("fixed","moving"):
            default[n]=_sanitize_rotated_roi(data.get(n),default[n])
    except Exception: pass
    return default
vertical_rois=load_vertical_config()
vertical_config_lock=threading.Lock()
def save_vertical_config():
    with vertical_config_lock: VERTICAL_CONFIG.write_text(json.dumps(vertical_rois,indent=2))

vertical_is_open=None
vertical_last_shift_px=None
vertical_last_gap_px=None
vertical_reference_gap_px=None
vertical_last_quality=None
vertical_last_check=None
vertical_last_error=""
vertical_fixed_tracked=None
vertical_moving_tracked=None
vertical_tracking_reason=""
vertical_moving_lost_count=0


def load_vertical2_config():
    default={
      "fixed":{"cx":0.45,"cy":0.35,"w":0.55,"h":0.035,"angle":0.0},
      "moving":{"cx":0.45,"cy":0.55,"w":0.55,"h":0.035,"angle":0.0},
    }
    try:
        data=json.loads(VERTICAL2_CONFIG.read_text())
        for n in ("fixed","moving"):
            default[n]=_sanitize_rotated_roi(data.get(n),default[n])
    except Exception:
        pass
    return default

vertical2_rois=load_vertical2_config()
vertical2_config_lock=threading.Lock()
def save_vertical2_config():
    with vertical2_config_lock:
        VERTICAL2_CONFIG.write_text(json.dumps(vertical2_rois,indent=2))

vertical2_is_open=None
vertical2_last_shift_px=None
vertical2_last_gap_px=None
vertical2_reference_gap_px=None
vertical2_last_quality=None
vertical2_last_check=None
vertical2_last_error=""
vertical2_fixed_tracked=None
vertical2_moving_tracked=None
vertical2_tracking_reason=""
vertical2_moving_lost_count=0


# ---------------------------------------------------------
# Personen-/Postboten-Bildbereich
# ---------------------------------------------------------

def _sanitize_person_roi(value):
    default = {"cx": 0.50, "cy": 0.50, "w": 0.50, "h": 0.80}
    if not isinstance(value, dict):
        return default
    try:
        w = min(0.98, max(0.01, float(value.get("w", default["w"]))))
        h = min(0.98, max(0.01, float(value.get("h", default["h"]))))
        cx = min(1.0 - w / 2.0, max(w / 2.0, float(value.get("cx", default["cx"]))))
        cy = min(1.0 - h / 2.0, max(h / 2.0, float(value.get("cy", default["cy"]))))
        return {"cx": cx, "cy": cy, "w": w, "h": h}
    except Exception:
        return default

def load_person_roi():
    try:
        return _sanitize_person_roi(json.loads(PERSON_ROI_CONFIG.read_text()))
    except Exception:
        return _sanitize_person_roi(None)

person_roi = load_person_roi()
person_roi_lock = threading.Lock()

def save_person_roi():
    with person_roi_lock:
        PERSON_ROI_CONFIG.write_text(json.dumps(person_roi, indent=2))

def save_door_config():
    with door_config_lock:
        DOOR_CONFIG.write_text(json.dumps(door_rois, indent=2))


# ---------------------------------------------------------
# MQTT Client
# ---------------------------------------------------------

c = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id="smartify-person-detection"
)

if USER:
    c.username_pw_set(USER, PW)

c.will_set(
    avail,
    "offline",
    retain=True
)


# ---------------------------------------------------------
# Timer
# ---------------------------------------------------------

post_timer = None
person_timer = None

# Haustuer-Laufzeitstatus
door_pause_until = 0.0
door_last_score = None
door_last_structure_score = None
door_last_gray_score = None
door_last_fixed_x = None
door_last_moving_x = None
door_last_gap_px = None
door_reference_gap_px = None
door_last_shift_px = None
door_last_edge_quality = None
door_last_check = None
door_is_open = None
door_last_error = ""
door_fixed_tracked = None
door_moving_tracked = None
door_tracking_reason = ""
door_moving_lost_count = 0
door_runtime_lock = threading.Lock()

# Die Kalibrier-WebUI ist nach App-Start zunaechst gesperrt.
# Erst ein HTML-Aufruf ueber Home-Assistant-Ingress ("Weboberflaeche oeffnen")
# schaltet sie fuer die konfigurierte Zeit frei.
calibration_ui_until = 0.0
calibration_ui_lock = threading.Lock()


def activate_calibration_ui():
    global calibration_ui_until
    with calibration_ui_lock:
        calibration_ui_until = time.monotonic() + DOOR_CALIBRATION_UI_SECONDS
        return DOOR_CALIBRATION_UI_SECONDS


def calibration_ui_remaining():
    with calibration_ui_lock:
        return max(0.0, calibration_ui_until - time.monotonic())


def calibration_ui_is_active():
    return calibration_ui_remaining() > 0.0


def touch_calibration_ui():
    # Nur echte Bedienaktionen verlaengern das 15-Minuten-Fenster.
    return activate_calibration_ui()
camera_fetch_lock = threading.Lock()
last_motion_signature = None


# ---------------------------------------------------------
# MQTT Discovery / frei waehlbare Entity-IDs
# ---------------------------------------------------------

LEGACY_UNIQUE_IDS = {
    "post": "smartify_person_detection_post",
    "person": "smartify_person_detection_person",
    "door": "smartify_person_detection_haustuer",
    "vertical": "smartify_person_detection_vertical",
    "vertical2": "smartify_person_detection_vertical2",
}
LEGACY_ENTITY_IDS = {
    "post": "binary_sensor.smartify_person_detection_post",
    "person": "binary_sensor.smartify_person_detection_person",
    "door": "binary_sensor.haustuer",
    "vertical": "binary_sensor.garagentor",
    "vertical2": "binary_sensor.garagentor_2",
}

def _validate_binary_entity_id(value, fallback):
    value = str(value or "").strip().lower()
    if re.fullmatch(r"binary_sensor\.[a-z0-9_]+", value):
        return value
    print(f"Ungueltige Binary-Entity-ID '{value}', verwende {fallback}.")
    return fallback

def _load_entity_identity():
    try:
        data=json.loads(ENTITY_IDENTITY_STATE.read_text())
        return data if isinstance(data,dict) else {}
    except Exception:
        return {}

def _save_entity_identity(data):
    ENTITY_IDENTITY_STATE.write_text(json.dumps(data,indent=2,sort_keys=True))

def _identity_for(kind, desired_entity_id, previous):
    prev=previous.get(kind) if isinstance(previous,dict) else None
    if isinstance(prev,dict) and prev.get("entity_id")==desired_entity_id and prev.get("unique_id"):
        return str(prev["unique_id"]), False
    if not isinstance(prev,dict):
        # Erstes Upgrade: bei unveraenderter ID die bestehende Unique-ID
        # beibehalten. Wurde die ID bereits in den neuen Optionen geaendert,
        # die alte Discovery sofort entfernen und eine neue Unique-ID anlegen.
        if desired_entity_id == LEGACY_ENTITY_IDS[kind]:
            return LEGACY_UNIQUE_IDS[kind], False
        digest=hashlib.sha1(desired_entity_id.encode("utf-8")).hexdigest()[:10]
        return f"smartify_person_detection_{kind}_{digest}", True
    digest=hashlib.sha1(desired_entity_id.encode("utf-8")).hexdigest()[:10]
    return f"smartify_person_detection_{kind}_{digest}", True

def _publish_binary_discovery(kind, topic, config, desired_entity_id, previous, new_state):
    unique_id, changed = _identity_for(kind, desired_entity_id, previous)
    if changed:
        # Leeres retained Config-Payload loescht die alte MQTT-Discovery-Entity.
        c.publish(topic, "", retain=True).wait_for_publish(timeout=3)
        time.sleep(0.05)
    config["unique_id"] = unique_id
    config["default_entity_id"] = desired_entity_id
    c.publish(topic, json.dumps(config), retain=True)
    new_state[kind] = {"entity_id": desired_entity_id, "unique_id": unique_id}

def discovery():

    dev = {
        "identifiers": [
            "smartify_person_detection"
        ],
        "name": "Smartify Person Detection",
        "manufacturer": "Smartify Your Home",
        "model": "YOLO11 Person & Post Detection"
    }


    previous_identity = _load_entity_identity()
    new_identity = dict(previous_identity)

    post_entity_id = _validate_binary_entity_id(POST_ENTITY_ID, "binary_sensor.smartify_person_detection_post")
    person_entity_id = _validate_binary_entity_id(PERSON_ENTITY_ID, "binary_sensor.smartify_person_detection_person")
    door_entity_id = _validate_binary_entity_id(DOOR_ENTITY_ID, "binary_sensor.haustuer")
    vertical_entity_id = _validate_binary_entity_id(VERTICAL_ENTITY_ID, "binary_sensor.garagentor")
    vertical2_entity_id = _validate_binary_entity_id(VERTICAL2_ENTITY_ID, "binary_sensor.garagentor_2")

    # -----------------------------------------------------
    # Binary Sensor: Post war da
    # -----------------------------------------------------

    post_binary_config = {
        "name": "Post war da",

        "state_topic": status,

        "payload_on": "ON",
        "payload_off": "OFF",

        "availability_topic": avail,

        "json_attributes_topic": post_attributes_topic,

        "device_class": "occupancy",

        "device": dev
    }

    _publish_binary_discovery(
        "post", f"{DISC}/binary_sensor/smartify_person_detection/post/config",
        post_binary_config, post_entity_id, previous_identity, new_identity
    )


    # -----------------------------------------------------
    # Binary Sensor: Person erkannt
    # -----------------------------------------------------

    person_binary_config = {
        "name": "Person erkannt",

        "state_topic": person_status,

        "payload_on": "ON",
        "payload_off": "OFF",

        "availability_topic": avail,

        "json_attributes_topic": person_attributes_topic,

        "device_class": "occupancy",

        "device": dev
    }

    _publish_binary_discovery(
        "person", f"{DISC}/binary_sensor/smartify_person_detection/person/config",
        person_binary_config, person_entity_id, previous_identity, new_identity
    )


    # -----------------------------------------------------
    # Binary Sensor: Haustuer
    # -----------------------------------------------------

    door_binary_config = {
        "name": DOOR_NAME,
        "state_topic": door_status_topic,
        "payload_on": "ON",
        "payload_off": "OFF",
        "availability_topic": avail,
        "json_attributes_topic": door_attributes_topic,
        "device_class": "door",
        "device": dev
    }

    _publish_binary_discovery(
        "door", f"{DISC}/binary_sensor/smartify_person_detection/haustuer/config",
        door_binary_config, door_entity_id, previous_identity, new_identity
    )

    if VERTICAL_ENABLED:
        vertical_binary_config = {
            "name": VERTICAL_NAME,
            "state_topic": vertical_status_topic,
            "payload_on": "ON", "payload_off": "OFF",
            "availability_topic": avail,
            "json_attributes_topic": vertical_attributes_topic,
            "device_class": "garage_door",
            "device": dev
        }
        _publish_binary_discovery(
            "vertical", f"{DISC}/binary_sensor/smartify_person_detection/vertical/config",
            vertical_binary_config, vertical_entity_id, previous_identity, new_identity
        )
    else:
        # Alte Discovery sauber entfernen, falls die Zusatzmessung deaktiviert wird.
        c.publish(f"{DISC}/binary_sensor/smartify_person_detection/vertical/config", "", retain=True)

    if VERTICAL2_ENABLED:
        vertical2_binary_config = {
            "name": VERTICAL2_NAME,
            "state_topic": vertical2_status_topic,
            "payload_on": "ON", "payload_off": "OFF",
            "availability_topic": avail,
            "json_attributes_topic": vertical2_attributes_topic,
            "device_class": "garage_door",
            "device": dev
        }
        _publish_binary_discovery(
            "vertical2", f"{DISC}/binary_sensor/smartify_person_detection/vertical2/config",
            vertical2_binary_config, vertical2_entity_id, previous_identity, new_identity
        )
    else:
        c.publish(f"{DISC}/binary_sensor/smartify_person_detection/vertical2/config", "", retain=True)

    _save_entity_identity(new_identity)

    # -----------------------------------------------------
    # Sensoren
    # -----------------------------------------------------

    sensors = [
        (
            "last_detection",
            "Letzte Postboten-Erkennung",
            last
        ),
        (
            "image",
            "Postboten Bild",
            image_topic
        ),
        (
            "yellow_ratio",
            "Gelbanteil",
            ratio_topic
        ),
        (
            "person_image",
            "Person Bild",
            person_image_topic
        )
    ]

    for oid, name, topic in sensors:

        config = {
            "name": name,
            "unique_id": f"smartify_person_detection_{oid}",
            "state_topic": topic,
            "availability_topic": avail,
            "device": dev
        }

        c.publish(
            f"{DISC}/sensor/smartify_person_detection/{oid}/config",
            json.dumps(config),
            retain=True
        )


# ---------------------------------------------------------
# Tageszaehler / Attribute
# ---------------------------------------------------------

def publish_counter_attributes():
    c.publish(
        person_attributes_topic,
        json.dumps(
            {
                "personen_heute": person_count_today,
                "letzte_10_detektionen": list(reversed(person_detection_history[-10:])),
                "snapshot": "/local/smartify_person_detection/person_latest.jpg"
            }
        ),
        retain=True
    )

    c.publish(
        post_attributes_topic,
        json.dumps(
            {
                "postboten_heute": post_count_today,
                "letzte_10_detektionen": list(reversed(post_detection_history[-10:])),
                "snapshot": "/local/smartify_person_detection/post_latest.jpg"
            }
        ),
        retain=True
    )


def check_daily_counter_reset():
    global counter_date
    global person_count_today
    global post_count_today
    global post_timer
    global person_timer

    today = local_date_string()

    if counter_date != today:
        counter_date = today
        person_count_today = 0
        post_count_today = 0

        if RESET_BINARIES_AT_MIDNIGHT:
            if post_timer:
                post_timer.cancel()
                post_timer = None

            if person_timer:
                person_timer.cancel()
                person_timer = None

            c.publish(status, "OFF", retain=True)
            c.publish(person_status, "OFF", retain=True)

        save_state()
        publish_counter_attributes()

        if RESET_BINARIES_AT_MIDNIGHT:
            print(
                "Tageszaehler und Post-/Person-Binary-Sensoren um Mitternacht zurueckgesetzt."
            )
        else:
            print(
                "Tageszaehler um Mitternacht zurueckgesetzt; Binary-Sensoren unveraendert."
            )


def _detection_timestamp():
    return datetime.now().astimezone().strftime("%d.%m.%Y %H:%M:%S")


def count_person():
    global person_count_today

    person_count_today += 1
    person_detection_history.append(_detection_timestamp())
    del person_detection_history[:-10]
    save_state()
    publish_counter_attributes()

    print(
        f"Personen heute: {person_count_today}"
    )


def count_post():
    global post_count_today

    post_count_today += 1
    post_detection_history.append(_detection_timestamp())
    del post_detection_history[:-10]
    save_state()
    publish_counter_attributes()

    print(
        f"Postboten heute: {post_count_today}"
    )


# ---------------------------------------------------------
# Haustuer: Kamera / ROI / Vergleich
# ---------------------------------------------------------

def camera_snapshot():
    if not SUPERVISOR_TOKEN:
        raise RuntimeError(
            "SUPERVISOR_TOKEN fehlt. homeassistant_api muss aktiviert sein."
        )

    entity = quote(
        DOOR_CAMERA_ENTITY,
        safe="._-"
    )

    url = (
        f"http://supervisor/core/api/camera_proxy/{entity}"
        f"?time={int(time.time() * 1000)}"
    )

    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Accept": "image/*"
        }
    )

    with camera_fetch_lock:
        with urlopen(req, timeout=15) as response:
            data = response.read()

    if not data:
        raise RuntimeError("Kamera lieferte kein Bild.")

    array = np.frombuffer(
        data,
        dtype=np.uint8
    )

    image = cv2.imdecode(
        array,
        cv2.IMREAD_COLOR
    )

    if image is None:
        raise RuntimeError("Kamerabild konnte nicht als Bild dekodiert werden.")

    return data, image


def normalized_rotated_roi(name):
    with door_config_lock:
        roi = dict(door_rois[name])

    fallback = {
        "fixed": {"cx": 0.714, "cy": 0.50, "w": 0.028, "h": 0.60, "angle": 0.0},
        "moving": {"cx": 0.746, "cy": 0.50, "w": 0.028, "h": 0.60, "angle": 0.0},
    }[name]
    return _sanitize_rotated_roi(roi, fallback)


def roi_geometry_pixels(image, name, roi_override=None):
    h_img, w_img = image.shape[:2]
    if roi_override is None:
        r = normalized_rotated_roi(name)
    else:
        fallback = normalized_rotated_roi(name)
        r = _sanitize_rotated_roi(roi_override, fallback)
    cx = float(r["cx"]) * w_img
    cy = float(r["cy"]) * h_img
    rw = max(8.0, float(r["w"]) * w_img)
    rh = max(12.0, float(r["h"]) * h_img)
    angle_deg = float(r.get("angle", 0.0))
    a = np.deg2rad(angle_deg)
    ex = np.array([np.cos(a), np.sin(a)], dtype=np.float32)
    ey = np.array([-np.sin(a), np.cos(a)], dtype=np.float32)
    center = np.array([cx, cy], dtype=np.float32)
    hx, hy = rw / 2.0, rh / 2.0
    tl = center - hx * ex - hy * ey
    tr = center + hx * ex - hy * ey
    br = center + hx * ex + hy * ey
    bl = center - hx * ex + hy * ey
    corners = np.array([tl, tr, br, bl], dtype=np.float32)
    return {
        "center": center,
        "width": rw,
        "height": rh,
        "angle_deg": angle_deg,
        "ex": ex,
        "ey": ey,
        "corners": corners,
    }


def roi_geometry_from_value(image, roi):
    h_img,w_img=image.shape[:2]
    r=_sanitize_rotated_roi(roi,{"cx":.5,"cy":.5,"w":.1,"h":.1,"angle":0.0})
    cx,cy=r["cx"]*w_img,r["cy"]*h_img; rw=max(12.0,r["w"]*w_img); rh=max(12.0,r["h"]*h_img)
    a=np.deg2rad(r.get("angle",0.0)); ex=np.array([np.cos(a),np.sin(a)],np.float32); ey=np.array([-np.sin(a),np.cos(a)],np.float32)
    center=np.array([cx,cy],np.float32); hx,hy=rw/2,rh/2
    corners=np.array([center-hx*ex-hy*ey,center+hx*ex-hy*ey,center+hx*ex+hy*ey,center-hx*ex+hy*ey],np.float32)
    return {"center":center,"width":rw,"height":rh,"angle_deg":float(r.get("angle",0)),"ex":ex,"ey":ey,"corners":corners}

def extract_rotated_roi_value(image, roi):
    geom=roi_geometry_from_value(image,roi); ow=max(12,int(round(geom["width"]))); oh=max(12,int(round(geom["height"])))
    dst=np.array([[0,0],[ow-1,0],[ow-1,oh-1],[0,oh-1]],np.float32)
    m=cv2.getPerspectiveTransform(geom["corners"],dst); inv=cv2.getPerspectiveTransform(dst,geom["corners"]); geom.update(matrix=m,inverse=inv,out_w=ow,out_h=oh)
    return cv2.warpPerspective(image,m,(ow,oh),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REPLICATE),geom

def extract_rotated_roi(image, name, roi_override=None):
    geom = roi_geometry_pixels(image, name, roi_override=roi_override)
    out_w = max(8, int(round(geom["width"])))
    out_h = max(12, int(round(geom["height"])))
    dst = np.array(
        [[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(geom["corners"], dst)
    inverse = cv2.getPerspectiveTransform(dst, geom["corners"])
    crop = cv2.warpPerspective(
        image,
        matrix,
        (out_w, out_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    if crop.size == 0:
        raise RuntimeError(f"Haustuer-ROI '{name}' ist leer oder ungueltig.")
    geom["matrix"] = matrix
    geom["inverse"] = inverse
    geom["out_w"] = out_w
    geom["out_h"] = out_h
    return crop, geom


DOOR_EDGE_UPSCALE = 2
DOOR_EDGE_PROFILE_SMOOTH = 7


def prepare_door_crop(crop):
    # 1.2.5-Verarbeitung bleibt erhalten. Das gedrehte ROI wird vorher
    # perspektivisch geradegezogen, sodass die gewuenschte Kante im Crop
    # wieder senkrecht steht.
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    gray = clahe.apply(gray)
    gray = cv2.resize(
        gray,
        None,
        fx=DOOR_EDGE_UPSCALE,
        fy=DOOR_EDGE_UPSCALE,
        interpolation=cv2.INTER_CUBIC,
    )
    return cv2.GaussianBlur(gray, (5, 5), 0)


def vertical_edge_profile(crop):
    gray = prepare_door_crop(crop)
    gx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    mag = np.abs(gx)
    h, w = mag.shape
    if w < 16 or h < 24:
        raise RuntimeError("Haustuer-Suchbereich ist fuer die Kantenerkennung zu klein.")
    y1 = max(1, int(round(h * 0.10)))
    y2 = min(h - 1, int(round(h * 0.90)))
    profile = np.median(mag[y1:y2, :], axis=0).astype(np.float32)
    signed_profile = np.median(gx[y1:y2, :], axis=0).astype(np.float32)
    if w >= DOOR_EDGE_PROFILE_SMOOTH:
        kernel = np.ones(DOOR_EDGE_PROFILE_SMOOTH, dtype=np.float32) / float(DOOR_EDGE_PROFILE_SMOOTH)
        profile = np.convolve(profile, kernel, mode="same")
        signed_profile = np.convolve(signed_profile, kernel, mode="same")
    return profile, signed_profile, mag


def subpixel_peak(profile, idx):
    idx = int(idx)
    if idx <= 0 or idx >= len(profile) - 1:
        return float(idx)
    y0, y1, y2 = float(profile[idx - 1]), float(profile[idx]), float(profile[idx + 1])
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-9:
        return float(idx)
    delta = min(max(0.5 * (y0 - y2) / denom, -0.5), 0.5)
    return float(idx) + float(delta)


def _profile_template(profile, idx, radius=8):
    idx = int(idx)
    vals = []
    for off in range(-radius, radius + 1):
        j = min(max(0, idx + off), len(profile) - 1)
        vals.append(float(profile[j]))
    a = np.asarray(vals, dtype=np.float32)
    a = a - float(np.mean(a))
    norm = float(np.linalg.norm(a))
    if norm > 1e-9:
        a = a / norm
    return [float(x) for x in a]


def _template_corr(profile, idx, template):
    if not template:
        return 1.0
    cur = np.asarray(_profile_template(profile, idx, radius=(len(template)-1)//2), dtype=np.float32)
    ref = np.asarray(template, dtype=np.float32)
    if cur.shape != ref.shape:
        return 0.0
    return float(np.clip(np.dot(cur, ref), -1.0, 1.0))


def _local_line_to_global(geom, local_x):
    pts = np.array(
        [[[float(local_x), 0.0], [float(local_x), float(geom["out_h"] - 1)]]],
        dtype=np.float32,
    )
    global_pts = cv2.perspectiveTransform(pts, geom["inverse"])[0]
    return global_pts[0].astype(np.float64), global_pts[1].astype(np.float64)


def _line_x_at_y(p1, p2, y):
    dy = float(p2[1] - p1[1])
    if abs(dy) < 1e-6:
        return float((p1[0] + p2[0]) / 2.0)
    t = (float(y) - float(p1[1])) / dy
    return float(p1[0] + t * (p2[0] - p1[0]))


def detect_edge_in_roi(image, name, roi_override=None, tracking=None):
    crop, geom = extract_rotated_roi(image, name, roi_override=roi_override)
    profile, signed_profile, mag = vertical_edge_profile(crop)
    w = len(profile)
    margin = max(2, min(5 * DOOR_EDGE_UPSCALE, int(round(w * 0.08))))
    lo, hi = margin, w - margin
    expected_idx = None
    if tracking and tracking.get("local_x") is not None:
        expected_idx = float(tracking["local_x"]) * DOOR_EDGE_UPSCALE
        half = DOOR_EDGE_TRACK_WINDOW_PX * DOOR_EDGE_UPSCALE
        lo = max(lo, int(np.floor(expected_idx - half)))
        hi = min(hi, int(np.ceil(expected_idx + half)) + 1)
    if hi - lo < 2:
        raise RuntimeError(f"Haustuer-Suchbereich '{name}' ist zu schmal.")
    idx = int(np.argmax(profile[lo:hi])) + lo
    local_x_upscaled = subpixel_peak(profile, idx)
    local_x = local_x_upscaled / float(DOOR_EDGE_UPSCALE)
    p1, p2 = _local_line_to_global(geom, local_x)
    baseline = float(np.median(profile)) + 1e-6
    strength = float(profile[idx])
    quality = strength / baseline
    signed = float(signed_profile[idx])
    polarity = 1 if signed >= 0 else -1
    corr = _template_corr(profile, idx, (tracking or {}).get("template"))
    tracked = True
    reason = ""
    if tracking:
        ref_pol = int(tracking.get("polarity", 0) or 0)
        if quality < DOOR_EDGE_MIN_QUALITY:
            tracked, reason = False, f"Qualitaet {quality:.2f} < {DOOR_EDGE_MIN_QUALITY:.2f}"
        # Die Hell-Dunkel-Richtung kann sich bei Tag/Nacht-Umschaltung,
        # IR-Filterwechsel oder starker Belichtungsanpassung umkehren.
        # Deshalb ist die Polaritaet nur noch Diagnoseinformation und kein
        # hartes Ausschlusskriterium. Entscheidend bleiben Position im
        # Suchfenster, Kantenqualitaet und Profilkorrelation.
        elif corr < DOOR_EDGE_MIN_TEMPLATE_CORR:
            tracked, reason = False, f"Profilkorrelation {corr:.2f} < {DOOR_EDGE_MIN_TEMPLATE_CORR:.2f}"
    return {
        "local_x": local_x,
        "quality": quality,
        "strength": strength,
        "polarity": polarity,
        "template_corr": corr,
        "tracked": tracked,
        "track_reason": reason,
        "expected_local_x": None if expected_idx is None else expected_idx / DOOR_EDGE_UPSCALE,
        "track_window_px": DOOR_EDGE_TRACK_WINDOW_PX,
        "profile_template": _profile_template(profile, idx),
        "line_p1": p1,
        "line_p2": p2,
        "geom": geom,
        "edge_mag": mag,
    }


def detect_door_edges(image, rois_override=None, reference=None):
    fixed_override = None if rois_override is None else rois_override.get("fixed")
    moving_override = None if rois_override is None else rois_override.get("moving")
    ftrack = None
    mtrack = None
    if reference:
        ftrack = {
            "local_x": reference.get("fixed_local_x"),
            "polarity": reference.get("fixed_polarity"),
            "template": reference.get("fixed_template"),
        }
        mtrack = {
            "local_x": reference.get("moving_local_x"),
            "polarity": reference.get("moving_polarity"),
            "template": reference.get("moving_template"),
        }
    fixed = detect_edge_in_roi(image, "fixed", roi_override=fixed_override, tracking=ftrack)
    moving = detect_edge_in_roi(image, "moving", roi_override=moving_override, tracking=mtrack)

    y_ref = float((fixed["geom"]["center"][1] + moving["geom"]["center"][1]) / 2.0)
    fixed_x = _line_x_at_y(fixed["line_p1"], fixed["line_p2"], y_ref)
    moving_x = _line_x_at_y(moving["line_p1"], moving["line_p2"], y_ref)
    gap = float(moving_x - fixed_x)
    if gap <= 2.0:
        raise RuntimeError("Tuerkante liegt nicht rechts von der Zargenkante. Beide ROI neu positionieren.")
    return {
        "fixed_x": fixed_x,
        "moving_x": moving_x,
        "gap_px": gap,
        "reference_y": y_ref,
        "quality": float(min(fixed["quality"], moving["quality"])),
        "fixed_quality": float(fixed["quality"]),
        "moving_quality": float(moving["quality"]),
        "fixed_tracked": bool(fixed["tracked"]),
        "moving_tracked": bool(moving["tracked"]),
        "tracking_ok": bool(fixed["tracked"] and moving["tracked"]),
        "tracking_reason": "; ".join(x for x in [
            ("Zarge: " + fixed["track_reason"]) if fixed["track_reason"] else "",
            ("Tuer: " + moving["track_reason"]) if moving["track_reason"] else "",
        ] if x),
        "fixed_strength": float(fixed["strength"]),
        "moving_strength": float(moving["strength"]),
        "fixed_line": [fixed["line_p1"].tolist(), fixed["line_p2"].tolist()],
        "moving_line": [moving["line_p1"].tolist(), moving["line_p2"].tolist()],
        "_fixed": fixed,
        "_moving": moving,
    }

def _debug_panel_from_edge(edge_data, title, orientation="vertical"):
    """Erzeugt einen grossen, gut lesbaren Debug-Ausschnitt des entzerrten ROI."""
    mag = edge_data["edge_mag"]
    mag8 = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    panel = cv2.cvtColor(mag8, cv2.COLOR_GRAY2BGR)

    # Die Scharr-Matrix liegt wegen DOOR_EDGE_UPSCALE in 2x vor. Die gefundene
    # Kante wird deshalb ebenfalls in diesem Koordinatensystem eingezeichnet.
    if orientation == "vertical":
        pos = int(round(float(edge_data["local_x"]) * DOOR_EDGE_UPSCALE))
        pos = max(0, min(panel.shape[1] - 1, pos))
        if edge_data.get("expected_local_x") is not None:
            exp = float(edge_data["expected_local_x"]) * DOOR_EDGE_UPSCALE
            half = float(edge_data.get("track_window_px", DOOR_EDGE_TRACK_WINDOW_PX)) * DOOR_EDGE_UPSCALE
            x1 = max(0, min(panel.shape[1]-1, int(round(exp-half))))
            x2 = max(0, min(panel.shape[1]-1, int(round(exp+half))))
            cv2.line(panel, (x1, 0), (x1, panel.shape[0]-1), (140,140,140), 1)
            cv2.line(panel, (x2, 0), (x2, panel.shape[0]-1), (140,140,140), 1)
        color = (255,255,255) if edge_data.get("tracked", True) else (80,80,80)
        cv2.line(panel, (pos, 0), (pos, panel.shape[0] - 1), color, 3, cv2.LINE_AA)
    else:
        pos = int(round(float(edge_data["local_y"]) * DOOR_EDGE_UPSCALE))
        pos = max(0, min(panel.shape[0] - 1, pos))
        cv2.line(panel, (0, pos), (panel.shape[1] - 1, pos), (255, 255, 255), 3, cv2.LINE_AA)

    # Mindestens ca. 360 px Breite je Panel, damit auch schmale ROI sichtbar sind.
    target_w = max(360, panel.shape[1] * 6)
    scale = target_w / float(panel.shape[1])
    target_h = max(140, int(round(panel.shape[0] * scale)))
    target_h = min(target_h, 760)
    panel = cv2.resize(panel, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

    header_h = 42
    out = np.zeros((panel.shape[0] + header_h, panel.shape[1], 3), dtype=np.uint8)
    out[header_h:, :] = panel
    cv2.putText(out, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (235, 235, 235), 2, cv2.LINE_AA)
    return out


def _compose_debug_panels(left, right, footer_lines):
    gap = 20
    footer_h = 34 * max(1, len(footer_lines)) + 16
    h = max(left.shape[0], right.shape[0])
    w = left.shape[1] + gap + right.shape[1]
    canvas = np.zeros((h + footer_h, w, 3), dtype=np.uint8)
    canvas[:left.shape[0], :left.shape[1]] = left
    x2 = left.shape[1] + gap
    canvas[:right.shape[0], x2:x2 + right.shape[1]] = right
    y = h + 28
    for line in footer_lines:
        cv2.putText(canvas, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (220, 220, 220), 1, cv2.LINE_AA)
        y += 32
    return canvas


def render_edge_view(image, rois_override=None):
    # 1.2.9: nicht mehr die winzigen ROI in ein schwarzes Vollbild zurueckwarpen.
    # Stattdessen werden die beiden entzerrten Scharr-Kantenbilder gross
    # nebeneinander dargestellt. So sieht man sofort konkurrierende Kanten.
    edges = detect_door_edges(image, rois_override=rois_override, reference=load_edge_reference())
    fixed = _debug_panel_from_edge(edges["_fixed"], "ZARGE - entzerrte Kantenansicht", "vertical")
    moving = _debug_panel_from_edge(edges["_moving"], "TUER - entzerrte Kantenansicht", "vertical")
    canvas = _compose_debug_panels(
        fixed,
        moving,
        [
            f"Zarge x={edges['fixed_x']:.2f}px   Tuer x={edges['moving_x']:.2f}px",
            f"Abstand={edges['gap_px']:.2f}px   Qualitaet={edges['quality']:.2f}",
            f"Tracking: {'OK' if edges['tracking_ok'] else 'KANTE VERLOREN'}" + ((" - " + edges['tracking_reason']) if edges['tracking_reason'] else ""),
            "Weisse Linie = erkannte Kante; graue Begrenzung = Suchfenster",
        ],
    )
    return canvas, edges

def horizontal_edge_profile(crop):
    gray = prepare_door_crop(crop)
    gy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    mag = np.abs(gy)
    h, w = mag.shape
    if w < 24 or h < 16:
        raise RuntimeError("Vertikaler Suchbereich ist zu klein.")
    x1 = max(1, int(round(w * 0.10)))
    x2 = min(w - 1, int(round(w * 0.90)))
    profile = np.median(mag[:, x1:x2], axis=1).astype(np.float32)
    signed_profile = np.median(gy[:, x1:x2], axis=1).astype(np.float32)
    if len(profile) >= DOOR_EDGE_PROFILE_SMOOTH:
        k = np.ones(DOOR_EDGE_PROFILE_SMOOTH, np.float32) / DOOR_EDGE_PROFILE_SMOOTH
        profile = np.convolve(profile, k, mode="same")
        signed_profile = np.convolve(signed_profile, k, mode="same")
    return profile, signed_profile, mag


def detect_horizontal_edge(image, roi, tracking=None):
    crop, geom = extract_rotated_roi_value(image, roi)
    profile, signed_profile, mag = horizontal_edge_profile(crop)
    h = len(profile)
    margin = max(2, min(5 * DOOR_EDGE_UPSCALE, int(round(h * 0.08))))
    lo, hi = margin, h - margin

    expected_idx = None
    if tracking and tracking.get("local_y") is not None:
        expected_idx = float(tracking["local_y"]) * DOOR_EDGE_UPSCALE
        half = DOOR_EDGE_TRACK_WINDOW_PX * DOOR_EDGE_UPSCALE
        lo = max(lo, int(np.floor(expected_idx - half)))
        hi = min(hi, int(np.ceil(expected_idx + half)) + 1)

    if hi - lo < 2:
        raise RuntimeError("Vertikaler Suchbereich ist zu schmal.")

    idx = int(np.argmax(profile[lo:hi])) + lo
    local_y = subpixel_peak(profile, idx) / float(DOOR_EDGE_UPSCALE)

    pts = np.array(
        [[[0.0, float(local_y)], [float(geom["out_w"] - 1), float(local_y)]]],
        np.float32,
    )
    gp = cv2.perspectiveTransform(pts, geom["inverse"])[0]

    baseline = float(np.median(profile)) + 1e-6
    strength = float(profile[idx])
    quality = strength / baseline
    polarity = 1 if float(signed_profile[idx]) >= 0 else -1
    corr = _template_corr(profile, idx, (tracking or {}).get("template"))

    tracked = True
    reason = ""
    if tracking:
        if quality < DOOR_EDGE_MIN_QUALITY:
            tracked = False
            reason = f"Qualitaet {quality:.2f} < {DOOR_EDGE_MIN_QUALITY:.2f}"
        elif corr < DOOR_EDGE_MIN_TEMPLATE_CORR:
            tracked = False
            reason = f"Profilkorrelation {corr:.2f} < {DOOR_EDGE_MIN_TEMPLATE_CORR:.2f}"

    return {
        "local_y": local_y,
        "quality": quality,
        "strength": strength,
        "polarity": polarity,
        "template_corr": corr,
        "tracked": tracked,
        "track_reason": reason,
        "expected_local_y": None if expected_idx is None else expected_idx / DOOR_EDGE_UPSCALE,
        "track_window_px": DOOR_EDGE_TRACK_WINDOW_PX,
        "profile_template": _profile_template(profile, idx),
        "line_p1": gp[0].astype(float),
        "line_p2": gp[1].astype(float),
        "geom": geom,
        "edge_mag": mag,
    }


def _line_y_at_x(p1, p2, x):
    dx = float(p2[0] - p1[0])
    if abs(dx) < 1e-6:
        return float((p1[1] + p2[1]) / 2.0)
    t = (float(x) - float(p1[0])) / dx
    return float(p1[1] + t * (p2[1] - p1[1]))


def detect_vertical_edges(image, rois_override=None, reference=None):
    rr = rois_override or vertical_rois
    ftrack = mtrack = None
    if reference:
        ftrack = {
            "local_y": reference.get("fixed_local_y"),
            "polarity": reference.get("fixed_polarity"),
            "template": reference.get("fixed_template"),
        }
        mtrack = {
            "local_y": reference.get("moving_local_y"),
            "polarity": reference.get("moving_polarity"),
            "template": reference.get("moving_template"),
        }

    fixed = detect_horizontal_edge(image, rr["fixed"], tracking=ftrack)
    moving = detect_horizontal_edge(image, rr["moving"], tracking=mtrack)

    xref = float((fixed["geom"]["center"][0] + moving["geom"]["center"][0]) / 2.0)
    fy = _line_y_at_x(fixed["line_p1"], fixed["line_p2"], xref)
    my = _line_y_at_x(moving["line_p1"], moving["line_p2"], xref)
    gap = float(my - fy)
    if abs(gap) <= 2.0:
        raise RuntimeError("Vertikale Referenzkanten liegen zu dicht zusammen.")

    return {
        "fixed_y": fy,
        "moving_y": my,
        "gap_px": gap,
        "reference_x": xref,
        "quality": float(min(fixed["quality"], moving["quality"])),
        "fixed_tracked": bool(fixed["tracked"]),
        "moving_tracked": bool(moving["tracked"]),
        "tracking_ok": bool(fixed["tracked"] and moving["tracked"]),
        "tracking_reason": "; ".join(x for x in [
            ("Fest: " + fixed["track_reason"]) if fixed["track_reason"] else "",
            ("Bewegt: " + moving["track_reason"]) if moving["track_reason"] else "",
        ] if x),
        "_fixed": fixed,
        "_moving": moving,
    }


def _debug_panel_horizontal_edge(edge_data, title):
    mag = edge_data["edge_mag"]
    mag8 = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    panel = cv2.cvtColor(mag8, cv2.COLOR_GRAY2BGR)

    pos = int(round(float(edge_data["local_y"]) * DOOR_EDGE_UPSCALE))
    pos = max(0, min(panel.shape[0] - 1, pos))

    if edge_data.get("expected_local_y") is not None:
        exp = float(edge_data["expected_local_y"]) * DOOR_EDGE_UPSCALE
        half = float(edge_data.get("track_window_px", DOOR_EDGE_TRACK_WINDOW_PX)) * DOOR_EDGE_UPSCALE
        y1 = max(0, min(panel.shape[0] - 1, int(round(exp - half))))
        y2 = max(0, min(panel.shape[0] - 1, int(round(exp + half))))
        cv2.line(panel, (0, y1), (panel.shape[1] - 1, y1), (140, 140, 140), 1)
        cv2.line(panel, (0, y2), (panel.shape[1] - 1, y2), (140, 140, 140), 1)

    color = (255, 255, 255) if edge_data.get("tracked", True) else (80, 80, 80)
    cv2.line(panel, (0, pos), (panel.shape[1] - 1, pos), color, 3, cv2.LINE_AA)

    target_w = max(420, panel.shape[1])
    scale = target_w / max(1, panel.shape[1])
    target_h = max(120, int(round(panel.shape[0] * scale)))
    panel = cv2.resize(panel, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

    header = np.zeros((42, panel.shape[1], 3), dtype=np.uint8)
    cv2.putText(header, title, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (230, 230, 230), 1, cv2.LINE_AA)
    return np.vstack([header, panel])


def _load_vertical_reference_file(path):
    try:
        data = json.loads(path.read_text())
        return {
            "gap_px": float(data["gap_px"]),
            "fixed_y": float(data["fixed_y"]),
            "moving_y": float(data["moving_y"]),
            "quality": float(data.get("quality", 0.0)),
            "fixed_local_y": float(data["fixed_local_y"]) if data.get("fixed_local_y") is not None else None,
            "moving_local_y": float(data["moving_local_y"]) if data.get("moving_local_y") is not None else None,
            "fixed_polarity": int(data.get("fixed_polarity", 0)),
            "moving_polarity": int(data.get("moving_polarity", 0)),
            "fixed_template": list(data.get("fixed_template", [])),
            "moving_template": list(data.get("moving_template", [])),
        }
    except Exception:
        return None


def _save_vertical_reference_file(path, edges):
    path.write_text(json.dumps({
        "gap_px": float(edges["gap_px"]),
        "fixed_y": float(edges["fixed_y"]),
        "moving_y": float(edges["moving_y"]),
        "quality": float(edges.get("quality", 0.0)),
        "fixed_local_y": float(edges["_fixed"]["local_y"]),
        "moving_local_y": float(edges["_moving"]["local_y"]),
        "fixed_polarity": int(edges["_fixed"]["polarity"]),
        "moving_polarity": int(edges["_moving"]["polarity"]),
        "fixed_template": edges["_fixed"]["profile_template"],
        "moving_template": edges["_moving"]["profile_template"],
    }, indent=2))


def load_vertical_reference():
    return _load_vertical_reference_file(VERTICAL_EDGE_REFERENCE)


def load_vertical2_reference():
    return _load_vertical_reference_file(VERTICAL2_EDGE_REFERENCE)


def render_vertical_edge_view(image, rois_override=None):
    ref = load_vertical_reference()
    e = detect_vertical_edges(image, rois_override, reference=ref)
    fixed = _debug_panel_horizontal_edge(e["_fixed"], "GARAGE 1 FEST - Tracking")
    moving = _debug_panel_horizontal_edge(e["_moving"], "GARAGE 1 BEWEGT - Tracking")
    canvas = _compose_debug_panels(
        fixed, moving,
        [
            f"Fest y={e['fixed_y']:.2f}px   Bewegt y={e['moving_y']:.2f}px",
            f"Abstand={e['gap_px']:.2f}px   Qualitaet={e['quality']:.2f}",
            f"Tracking: {'OK' if e['tracking_ok'] else 'KANTE VERLOREN'}"
            + ((" - " + e["tracking_reason"]) if e["tracking_reason"] else ""),
            "Weisse Linie = erkannte Kante; graue Begrenzung = Suchfenster",
        ],
    )
    return canvas, e


def render_vertical2_edge_view(image, rois_override=None):
    ref = load_vertical2_reference()
    e = detect_vertical_edges(image, rois_override or vertical2_rois, reference=ref)
    fixed = _debug_panel_horizontal_edge(e["_fixed"], "GARAGE 2 FEST - Tracking")
    moving = _debug_panel_horizontal_edge(e["_moving"], "GARAGE 2 BEWEGT - Tracking")
    canvas = _compose_debug_panels(
        fixed, moving,
        [
            f"Fest y={e['fixed_y']:.2f}px   Bewegt y={e['moving_y']:.2f}px",
            f"Abstand={e['gap_px']:.2f}px   Qualitaet={e['quality']:.2f}",
            f"Tracking: {'OK' if e['tracking_ok'] else 'KANTE VERLOREN'}"
            + ((" - " + e["tracking_reason"]) if e["tracking_reason"] else ""),
            "Weisse Linie = erkannte Kante; graue Begrenzung = Suchfenster",
        ],
    )
    return canvas, e


def _calibrate_vertical_common(image, rois, ref_image_path, ref_data_path, label):
    usable, reason = _door_image_usable(image)
    if not usable:
        raise RuntimeError(f"Kamerabild unbrauchbar: {reason}")
    e = detect_vertical_edges(image, rois, reference=None)
    if not cv2.imwrite(str(ref_image_path), image):
        raise RuntimeError(f"{label}-Referenzbild konnte nicht gespeichert werden.")
    _save_vertical_reference_file(ref_data_path, e)
    return e


def calibrate_vertical(image=None):
    global vertical_is_open, vertical_last_shift_px, vertical_last_gap_px
    global vertical_reference_gap_px, vertical_last_quality, vertical_last_check
    global vertical_last_error, vertical_fixed_tracked, vertical_moving_tracked
    global vertical_tracking_reason, vertical_moving_lost_count

    if image is None:
        _, image = camera_snapshot()
    e = _calibrate_vertical_common(
        image, vertical_rois, VERTICAL_REFERENCE, VERTICAL_EDGE_REFERENCE, VERTICAL_NAME
    )
    vertical_is_open = False
    vertical_last_shift_px = 0.0
    vertical_last_gap_px = e["gap_px"]
    vertical_reference_gap_px = e["gap_px"]
    vertical_last_quality = e["quality"]
    vertical_last_check = datetime.now().astimezone().isoformat(timespec="seconds")
    vertical_last_error = ""
    vertical_fixed_tracked = True
    vertical_moving_tracked = True
    vertical_tracking_reason = ""
    vertical_moving_lost_count = 0
    publish_vertical_state()


def calibrate_vertical2(image=None):
    global vertical2_is_open, vertical2_last_shift_px, vertical2_last_gap_px
    global vertical2_reference_gap_px, vertical2_last_quality, vertical2_last_check
    global vertical2_last_error, vertical2_fixed_tracked, vertical2_moving_tracked
    global vertical2_tracking_reason, vertical2_moving_lost_count

    if image is None:
        _, image = camera_snapshot()
    e = _calibrate_vertical_common(
        image, vertical2_rois, VERTICAL2_REFERENCE, VERTICAL2_EDGE_REFERENCE, VERTICAL2_NAME
    )
    vertical2_is_open = False
    vertical2_last_shift_px = 0.0
    vertical2_last_gap_px = e["gap_px"]
    vertical2_reference_gap_px = e["gap_px"]
    vertical2_last_quality = e["quality"]
    vertical2_last_check = datetime.now().astimezone().isoformat(timespec="seconds")
    vertical2_last_error = ""
    vertical2_fixed_tracked = True
    vertical2_moving_tracked = True
    vertical2_tracking_reason = ""
    vertical2_moving_lost_count = 0
    publish_vertical2_state()


def publish_vertical_state():
    if not VERTICAL_ENABLED:
        return
    c.publish(vertical_status_topic, "ON" if vertical_is_open else "OFF", retain=True)
    attrs = {
        "messrichtung": "vertikal",
        "kalibriert": VERTICAL_EDGE_REFERENCE.exists(),
        "verschiebung_px": vertical_last_shift_px,
        "kantenabstand_px": vertical_last_gap_px,
        "referenzabstand_px": vertical_reference_gap_px,
        "kantenqualitaet": vertical_last_quality,
        "tracking_suchfenster_px": DOOR_EDGE_TRACK_WINDOW_PX,
        "tracking_min_qualitaet": DOOR_EDGE_MIN_QUALITY,
        "tracking_min_profilkorrelation": DOOR_EDGE_MIN_TEMPLATE_CORR,
        "letzte_pruefung": vertical_last_check,
    }
    if vertical_fixed_tracked is not None:
        attrs["feste_kante_tracking"] = "ok" if vertical_fixed_tracked else "verloren"
    if vertical_moving_tracked is not None:
        attrs["bewegte_kante_tracking"] = "ok" if vertical_moving_tracked else "verloren"
    if vertical_tracking_reason:
        attrs["tracking_hinweis"] = vertical_tracking_reason
    if vertical_last_error:
        attrs["fehler"] = vertical_last_error
    c.publish(vertical_attributes_topic, json.dumps(attrs), retain=True)


def publish_vertical2_state():
    if not VERTICAL2_ENABLED:
        return
    c.publish(vertical2_status_topic, "ON" if vertical2_is_open else "OFF", retain=True)
    attrs = {
        "messrichtung": "vertikal",
        "kalibriert": VERTICAL2_EDGE_REFERENCE.exists(),
        "verschiebung_px": vertical2_last_shift_px,
        "kantenabstand_px": vertical2_last_gap_px,
        "referenzabstand_px": vertical2_reference_gap_px,
        "kantenqualitaet": vertical2_last_quality,
        "tracking_suchfenster_px": DOOR_EDGE_TRACK_WINDOW_PX,
        "tracking_min_qualitaet": DOOR_EDGE_MIN_QUALITY,
        "tracking_min_profilkorrelation": DOOR_EDGE_MIN_TEMPLATE_CORR,
        "letzte_pruefung": vertical2_last_check,
    }
    if vertical2_fixed_tracked is not None:
        attrs["feste_kante_tracking"] = "ok" if vertical2_fixed_tracked else "verloren"
    if vertical2_moving_tracked is not None:
        attrs["bewegte_kante_tracking"] = "ok" if vertical2_moving_tracked else "verloren"
    if vertical2_tracking_reason:
        attrs["tracking_hinweis"] = vertical2_tracking_reason
    if vertical2_last_error:
        attrs["fehler"] = vertical2_last_error
    c.publish(vertical2_attributes_topic, json.dumps(attrs), retain=True)


def _check_vertical_common(
    image, rois, reference, current_open, open_shift, close_shift,
    label, lost_count
):
    usable, reason = _door_image_usable(image)
    if not usable:
        return {"discarded": True, "error": f"Kamerabild unbrauchbar: {reason}"}

    e = detect_vertical_edges(image, rois, reference=reference)
    shift = float(e["gap_px"] - float(reference["gap_px"]))
    fixed_ok = bool(e["fixed_tracked"])
    moving_ok = bool(e["moving_tracked"])

    if not fixed_ok:
        return {
            "discarded": True,
            "error": "Feste Garagentorkante verloren; Zustand beibehalten",
            "edges": e, "shift": shift, "lost_count": 0,
        }

    if fixed_ok and not moving_ok:
        lost_count += 1
        if lost_count < 2:
            return {
                "discarded": True,
                "error": "Bewegte Garagentorkante einmal verloren; warte auf Bestaetigung",
                "edges": e, "shift": shift, "lost_count": lost_count,
            }
        is_open = True
    else:
        lost_count = 0
        is_open = shift > close_shift if current_open is True else shift >= open_shift

    return {
        "discarded": False,
        "open": is_open,
        "edges": e,
        "shift": shift,
        "lost_count": lost_count,
    }


def check_vertical(image=None, force=False):
    global vertical_is_open, vertical_last_shift_px, vertical_last_gap_px
    global vertical_reference_gap_px, vertical_last_quality, vertical_last_check
    global vertical_last_error, vertical_fixed_tracked, vertical_moving_tracked
    global vertical_tracking_reason, vertical_moving_lost_count

    if not VERTICAL_ENABLED or not VERTICAL_EDGE_REFERENCE.exists():
        return None
    try:
        if image is None:
            _, image = camera_snapshot()
        ref = load_vertical_reference()
        if ref is None:
            raise RuntimeError("Keine gueltige Garagentor-Kantenreferenz vorhanden. Neu kalibrieren.")

        r = _check_vertical_common(
            image, vertical_rois, ref, vertical_is_open,
            VERTICAL_OPEN_SHIFT_PX, VERTICAL_CLOSE_SHIFT_PX,
            VERTICAL_NAME, vertical_moving_lost_count
        )
        vertical_moving_lost_count = r.get("lost_count", vertical_moving_lost_count)
        vertical_last_check = datetime.now().astimezone().isoformat(timespec="seconds")

        if "edges" in r:
            e = r["edges"]
            vertical_last_shift_px = r["shift"]
            vertical_last_gap_px = e["gap_px"]
            vertical_reference_gap_px = float(ref["gap_px"])
            vertical_last_quality = e["quality"]
            vertical_fixed_tracked = e["fixed_tracked"]
            vertical_moving_tracked = e["moving_tracked"]
            vertical_tracking_reason = e["tracking_reason"]

        if r["discarded"]:
            vertical_last_error = r["error"]
            publish_vertical_state()
            print(f"{VERTICAL_NAME}: {r['error']}")
            return None

        vertical_is_open = r["open"]
        vertical_last_error = ""
        publish_vertical_state()
        e = r["edges"]
        print(
            f"{VERTICAL_NAME}: {'OFFEN' if vertical_is_open else 'geschlossen'}, "
            f"Fest y={e['fixed_y']:.2f}px, Bewegt y={e['moving_y']:.2f}px, "
            f"Verschiebung={r['shift']:+.2f}px, Abstand={e['gap_px']:.2f}px, "
            f"Referenz={ref['gap_px']:.2f}px, Qualitaet={e['quality']:.2f}, "
            f"Tracking={'OK' if e['tracking_ok'] else 'VERLOREN'}"
        )
        return vertical_is_open, r["shift"]
    except Exception as exc:
        vertical_last_error = str(exc)
        publish_vertical_state()
        print(f"Fehler bei {VERTICAL_NAME}-Pruefung:", exc)
        return None


def check_vertical2(image=None, force=False):
    global vertical2_is_open, vertical2_last_shift_px, vertical2_last_gap_px
    global vertical2_reference_gap_px, vertical2_last_quality, vertical2_last_check
    global vertical2_last_error, vertical2_fixed_tracked, vertical2_moving_tracked
    global vertical2_tracking_reason, vertical2_moving_lost_count

    if not VERTICAL2_ENABLED or not VERTICAL2_EDGE_REFERENCE.exists():
        return None
    try:
        if image is None:
            _, image = camera_snapshot()
        ref = load_vertical2_reference()
        if ref is None:
            raise RuntimeError("Keine gueltige Garagentor-2-Kantenreferenz vorhanden. Neu kalibrieren.")

        r = _check_vertical_common(
            image, vertical2_rois, ref, vertical2_is_open,
            VERTICAL2_OPEN_SHIFT_PX, VERTICAL2_CLOSE_SHIFT_PX,
            VERTICAL2_NAME, vertical2_moving_lost_count
        )
        vertical2_moving_lost_count = r.get("lost_count", vertical2_moving_lost_count)
        vertical2_last_check = datetime.now().astimezone().isoformat(timespec="seconds")

        if "edges" in r:
            e = r["edges"]
            vertical2_last_shift_px = r["shift"]
            vertical2_last_gap_px = e["gap_px"]
            vertical2_reference_gap_px = float(ref["gap_px"])
            vertical2_last_quality = e["quality"]
            vertical2_fixed_tracked = e["fixed_tracked"]
            vertical2_moving_tracked = e["moving_tracked"]
            vertical2_tracking_reason = e["tracking_reason"]

        if r["discarded"]:
            vertical2_last_error = r["error"]
            publish_vertical2_state()
            print(f"{VERTICAL2_NAME}: {r['error']}")
            return None

        vertical2_is_open = r["open"]
        vertical2_last_error = ""
        publish_vertical2_state()
        e = r["edges"]
        print(
            f"{VERTICAL2_NAME}: {'OFFEN' if vertical2_is_open else 'geschlossen'}, "
            f"Fest y={e['fixed_y']:.2f}px, Bewegt y={e['moving_y']:.2f}px, "
            f"Verschiebung={r['shift']:+.2f}px, Abstand={e['gap_px']:.2f}px, "
            f"Referenz={ref['gap_px']:.2f}px, Qualitaet={e['quality']:.2f}, "
            f"Tracking={'OK' if e['tracking_ok'] else 'VERLOREN'}"
        )
        return vertical2_is_open, r["shift"]
    except Exception as exc:
        vertical2_last_error = str(exc)
        publish_vertical2_state()
        print(f"Fehler bei {VERTICAL2_NAME}-Pruefung:", exc)
        return None


def load_edge_reference():
    try:
        data = json.loads(DOOR_EDGE_REFERENCE.read_text())
        return {
            "fixed_x": float(data["fixed_x"]),
            "moving_x": float(data["moving_x"]),
            "gap_px": float(data["gap_px"]),
            "quality": float(data.get("quality", 0.0)),
            "fixed_local_x": float(data["fixed_local_x"]),
            "moving_local_x": float(data["moving_local_x"]),
            "fixed_polarity": int(data.get("fixed_polarity", 0)),
            "moving_polarity": int(data.get("moving_polarity", 0)),
            "fixed_template": list(data.get("fixed_template", [])),
            "moving_template": list(data.get("moving_template", [])),
        }
    except Exception:
        return None


def save_edge_reference(edges):
    DOOR_EDGE_REFERENCE.write_text(
        json.dumps(
            {
                "fixed_x": float(edges["fixed_x"]),
                "moving_x": float(edges["moving_x"]),
                "gap_px": float(edges["gap_px"]),
                "quality": float(edges.get("quality", 0.0)),
                "fixed_local_x": float(edges["_fixed"]["local_x"]),
                "moving_local_x": float(edges["_moving"]["local_x"]),
                "fixed_polarity": int(edges["_fixed"]["polarity"]),
                "moving_polarity": int(edges["_moving"]["polarity"]),
                "fixed_template": edges["_fixed"]["profile_template"],
                "moving_template": edges["_moving"]["profile_template"],
            },
            indent=2
        )
    )


def calculate_door_geometry(current):
    reference = load_edge_reference()
    if reference is None:
        raise RuntimeError("Keine Kantenreferenz vorhanden. Tuer geschlossen neu kalibrieren.")
    edges = detect_door_edges(current, reference=reference)
    shift_px = float(edges["gap_px"] - reference["gap_px"])
    return reference, edges, shift_px

def publish_door_state(
    is_open,
    shift_px=None,
    fixed_x=None,
    moving_x=None,
    gap_px=None,
    reference_gap_px=None,
    edge_quality=None,
    fixed_tracked=None,
    moving_tracked=None,
    tracking_reason="",
    error=""
):
    global door_is_open
    global door_last_score
    global door_last_structure_score
    global door_last_gray_score
    global door_last_fixed_x
    global door_last_moving_x
    global door_last_gap_px
    global door_reference_gap_px
    global door_last_shift_px
    global door_last_edge_quality
    global door_last_check
    global door_last_error
    global door_fixed_tracked
    global door_moving_tracked
    global door_tracking_reason

    door_is_open = bool(is_open)
    door_last_score = shift_px
    door_last_structure_score = None
    door_last_gray_score = None
    door_last_fixed_x = fixed_x
    door_last_moving_x = moving_x
    door_last_gap_px = gap_px
    door_reference_gap_px = reference_gap_px
    door_last_shift_px = shift_px
    door_last_edge_quality = edge_quality
    door_fixed_tracked = fixed_tracked
    door_moving_tracked = moving_tracked
    door_tracking_reason = tracking_reason
    door_last_check = (
        datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    )
    door_last_error = error

    c.publish(door_status_topic, "ON" if door_is_open else "OFF", retain=True)
    publish_door_attributes_only()


def publish_door_attributes_only():
    attrs = {
        "kamera": DOOR_CAMERA_ENTITY,
        "kalibriert": DOOR_EDGE_REFERENCE.exists(),
        "pruefintervall_s": DOOR_CHECK_INTERVAL,
        "pause_nach_bewegung_s": DOOR_PAUSE_AFTER_MOTION,
        "vergleich": "Geometrie: zwei getrennte drehbare ROI; intern geradegerichtet und auf gemeinsame Bildhoehe zurueckgerechnet",
        "offen_ab_verschiebung_px": DOOR_OPEN_SHIFT_PX,
        "geschlossen_bis_verschiebung_px": DOOR_CLOSE_SHIFT_PX,
        "tracking_suchfenster_px": DOOR_EDGE_TRACK_WINDOW_PX,
        "tracking_min_qualitaet": DOOR_EDGE_MIN_QUALITY,
        "tracking_min_profilkorrelation": DOOR_EDGE_MIN_TEMPLATE_CORR,
        "letzte_pruefung": door_last_check
    }

    if door_last_fixed_x is not None:
        attrs["zargenkante_x"] = round(float(door_last_fixed_x), 2)
    if door_last_moving_x is not None:
        attrs["tuerkante_x"] = round(float(door_last_moving_x), 2)
    if door_last_gap_px is not None:
        attrs["kantenabstand_px"] = round(float(door_last_gap_px), 2)
    if door_reference_gap_px is not None:
        attrs["referenzabstand_px"] = round(float(door_reference_gap_px), 2)
    if door_last_shift_px is not None:
        attrs["verschiebung_px"] = round(float(door_last_shift_px), 2)
    if door_last_edge_quality is not None:
        attrs["kantenqualitaet"] = round(float(door_last_edge_quality), 2)
    if door_fixed_tracked is not None:
        attrs["zargenkante_tracking"] = "ok" if door_fixed_tracked else "verloren"
    if door_moving_tracked is not None:
        attrs["tuerkante_tracking"] = "ok" if door_moving_tracked else "verloren"
    if door_tracking_reason:
        attrs["tracking_hinweis"] = door_tracking_reason
    if door_last_error:
        attrs["fehler"] = door_last_error

    c.publish(door_attributes_topic, json.dumps(attrs), retain=True)


def calibrate_closed_door(image=None):
    if image is None:
        _, image = camera_snapshot()

    edges = detect_door_edges(image)

    ok = cv2.imwrite(str(DOOR_REFERENCE), image)
    if not ok:
        raise RuntimeError("Referenzbild konnte nicht gespeichert werden.")

    save_edge_reference(edges)

    publish_door_state(
        False,
        shift_px=0.0,
        fixed_x=edges["fixed_x"],
        moving_x=edges["moving_x"],
        gap_px=edges["gap_px"],
        reference_gap_px=edges["gap_px"],
        edge_quality=edges["quality"],
        fixed_tracked=True,
        moving_tracked=True,
        tracking_reason=""
    )

    print(
        "Haustuer: geschlossene Kantenreferenz kalibriert: "
        f"Zarge x={edges['fixed_x']:.2f}, Tuer x={edges['moving_x']:.2f}, "
        f"Abstand={edges['gap_px']:.2f}px, Qualitaet={edges['quality']:.2f}."
    )


def _door_image_usable(image):
    """Sehr grobe Plausibilitaetspruefung gegen Leer-/Placeholder-Bilder.

    Absichtlich tolerant, damit Tag/Nacht-Bilder nicht faelschlich verworfen
    werden. Abgelehnt werden nur leere, winzige oder nahezu strukturlose Frames.
    """
    if image is None or not isinstance(image, np.ndarray) or image.size == 0:
        return False, "kein Bild"
    if image.ndim < 2 or image.shape[0] < 100 or image.shape[1] < 100:
        return False, f"Bild zu klein ({getattr(image, 'shape', None)})"
    try:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
        p5, p95 = np.percentile(gray, [5, 95])
        std = float(np.std(gray))
        if std < 3.0 or float(p95 - p5) < 8.0:
            return False, f"Bild nahezu strukturlos (std={std:.1f}, dyn={float(p95-p5):.1f})"
    except Exception as exc:
        return False, f"Bildpruefung fehlgeschlagen: {exc}"
    return True, ""


def check_door(force=False, image=None):
    global door_last_error, door_moving_lost_count

    if not DOOR_ENABLED:
        return None

    if not DOOR_EDGE_REFERENCE.exists():
        publish_door_attributes_only()
        return None

    if not force and time.monotonic() < door_pause_until:
        return None

    try:
        if image is None:
            _, image = camera_snapshot()
        usable, unusable_reason = _door_image_usable(image)
        if not usable:
            with door_runtime_lock:
                door_last_error = f"Kamerabild unbrauchbar: {unusable_reason}"
            publish_door_attributes_only()
            print(f"Haustuer: Messung verworfen, Zustand unveraendert ({unusable_reason}).")
            return None

        reference, edges, shift_px = calculate_door_geometry(image)

        # 1.4.1: Ein unbrauchbares Bild bzw. eine verlorene feste Zargenkante
        # darf den Tuerstatus NICHT auf offen setzen. Nur wenn die feste Kante
        # weiterhin sicher erkannt wird und die bewegliche Tuerkante wiederholt
        # verschwindet, wird das als reale Oeffnung gewertet.
        tracking_ok = bool(edges["tracking_ok"])
        fixed_ok = bool(edges.get("fixed_tracked"))
        moving_ok = bool(edges.get("moving_tracked"))

        if not fixed_ok:
            door_moving_lost_count = 0
            with door_runtime_lock:
                door_last_error = "Zargenkante verloren; Zustand beibehalten"
                globals()["door_last_fixed_x"] = edges.get("fixed_x")
                globals()["door_last_moving_x"] = edges.get("moving_x")
                globals()["door_last_gap_px"] = edges.get("gap_px")
                globals()["door_reference_gap_px"] = reference.get("gap_px")
                globals()["door_last_shift_px"] = shift_px
                globals()["door_last_edge_quality"] = edges.get("quality")
                globals()["door_fixed_tracked"] = fixed_ok
                globals()["door_moving_tracked"] = moving_ok
                globals()["door_tracking_reason"] = edges.get("tracking_reason", "")
                globals()["door_last_check"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
            publish_door_attributes_only()
            print(
                "Haustuer: Zargenkante verloren; Messung ungueltig, "
                "bisheriger Zustand bleibt unveraendert."
            )
            return None

        if fixed_ok and not moving_ok:
            door_moving_lost_count += 1
            if door_moving_lost_count < 2:
                with door_runtime_lock:
                    door_last_error = "Tuerkante einmal verloren; warte auf Bestaetigung"
                    globals()["door_fixed_tracked"] = fixed_ok
                    globals()["door_moving_tracked"] = moving_ok
                    globals()["door_tracking_reason"] = edges.get("tracking_reason", "")
                    globals()["door_last_check"] = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                publish_door_attributes_only()
                print("Haustuer: Tuerkante einmal verloren; Zustand noch unveraendert.")
                return None
            is_open = True
        else:
            door_moving_lost_count = 0
            if door_is_open is True:
                is_open = shift_px > DOOR_CLOSE_SHIFT_PX
            else:
                is_open = shift_px >= DOOR_OPEN_SHIFT_PX

        publish_door_state(
            is_open,
            shift_px=shift_px,
            fixed_x=edges["fixed_x"],
            moving_x=edges["moving_x"],
            gap_px=edges["gap_px"],
            reference_gap_px=reference["gap_px"],
            edge_quality=edges["quality"],
            fixed_tracked=edges["fixed_tracked"],
            moving_tracked=edges["moving_tracked"],
            tracking_reason=edges["tracking_reason"]
        )

        track_text = "OK" if tracking_ok else f"VERLOREN ({edges['tracking_reason']})"
        print(
            f"Haustuer: {'OFFEN' if is_open else 'geschlossen'}, "
            f"Zarge x={edges['fixed_x']:.2f}px, Tuer x={edges['moving_x']:.2f}px, "
            f"Verschiebung={shift_px:+.2f}px, "
            f"Abstand={edges['gap_px']:.2f}px, Referenz={reference['gap_px']:.2f}px, "
            f"Qualitaet={edges['quality']:.2f}, Tracking={track_text}, "
            f"Grenzen offen>={DOOR_OPEN_SHIFT_PX:.2f}px / zu<={DOOR_CLOSE_SHIFT_PX:.2f}px"
        )

        return is_open, shift_px

    except Exception as e:
        error = str(e)
        with door_runtime_lock:
            door_last_error = error
        publish_door_attributes_only()
        print("Fehler bei Haustuer-Pruefung:", error)
        return None


def pause_door_after_motion():
    global door_pause_until

    if not DOOR_ENABLED:
        return

    door_pause_until = max(
        door_pause_until,
        time.monotonic() + DOOR_PAUSE_AFTER_MOTION
    )


def door_worker():
    if not DOOR_ENABLED:
        print("Haustuer-Erkennung deaktiviert.")
        return

    print(
        f"Haustuer-Pruefung aktiv: {DOOR_CAMERA_ENTITY}, "
        f"alle {DOOR_CHECK_INTERVAL}s"
    )

    next_check = time.monotonic() + 2.0

    while True:
        try:
            now = time.monotonic()

            if now >= next_check:
                if now < door_pause_until:
                    remaining = max(
                        0.0,
                        door_pause_until - now
                    )

                    print(
                        f"Haustuer-Pruefung pausiert wegen Bewegung "
                        f"({remaining:.0f}s verbleibend)."
                    )

                    next_check = door_pause_until + 0.5
                else:
                    _, shared_image = camera_snapshot()
                    check_door(image=shared_image)
                    if VERTICAL_ENABLED:
                        check_vertical(image=shared_image)
                    if VERTICAL2_ENABLED:
                        check_vertical2(image=shared_image)
                    next_check = time.monotonic() + DOOR_CHECK_INTERVAL

            time.sleep(1.0)

        except Exception as e:
            print(
                "Fehler im Haustuer-Worker:",
                e
            )
            time.sleep(2.0)


# ---------------------------------------------------------
# Haustuer: Ingress-Kalibrieroberflaeche
# ---------------------------------------------------------

DOOR_UI_HTML = r'''<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Smartify Person Detection – Kalibrierung</title>
<style>
:root{color-scheme:dark;background:#111;color:#eee;font-family:system-ui,sans-serif}*{box-sizing:border-box}body{margin:0;padding:14px;background:#111;color:#eee}main{max-width:1100px;margin:auto}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:10px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px 16px}.panel{background:#1d1d1d;border:1px solid #333;border-radius:12px;padding:12px;margin:12px 0;line-height:1.35}.panel h3{margin:0 0 8px;font-size:1.05rem}button{font:inherit;padding:10px 14px;border:0;border-radius:9px;background:#2f6fed;color:#fff;cursor:pointer;min-height:42px}button.secondary{background:#444}button.active{outline:2px solid #fff}input{font:inherit;padding:7px;background:#222;color:#eee;border:1px solid #555;border-radius:6px;max-width:100%}code{font-size:.92em;overflow-wrap:anywhere}#msg{min-height:1.4em;color:#9fe8a7;margin:8px 0}.hint{color:#bbb;font-size:.9em;margin:8px 0;line-height:1.35}
#stage{position:relative;width:100%;line-height:0;user-select:none;touch-action:none;background:#000;border-radius:10px;overflow:hidden;min-height:80px}#cam{display:block;width:100%;height:auto}.roi{position:absolute;box-sizing:border-box;cursor:move;touch-action:none;border:2px solid;background:rgba(255,255,255,.07);transform-origin:center center}.roi.fixed{border-color:#00e5ff;background:rgba(0,229,255,.10)}.roi.moving{border-color:#ffb300;background:rgba(255,179,0,.10)}.roi.garageFixed{border-color:#76ff03;background:rgba(118,255,3,.10)}.roi.garageMoving{border-color:#e040fb;background:rgba(224,64,251,.10)}.roi.garage2Fixed{border-color:#40c4ff;background:rgba(64,196,255,.10)}.roi.garage2Moving{border-color:#ff4081;background:rgba(255,64,129,.10)}.roi.personArea{border-color:#7c4dff;background:rgba(124,77,255,.10)}.label{position:absolute;left:2px;top:2px;line-height:1.2;font:700 11px system-ui;padding:2px 4px;border-radius:4px;color:#000;pointer-events:none}.fixed .label{background:#00e5ff}.moving .label{background:#ffb300}.garageFixed .label{background:#76ff03}.garageMoving .label{background:#e040fb}.garage2Fixed .label{background:#40c4ff}.garage2Moving .label{background:#ff4081}.personArea .label{background:#b388ff}.handle{position:absolute;width:14px;height:14px;border:0;background:transparent!important;border-radius:0;box-sizing:border-box}.nw{left:-7px;top:-7px;cursor:nwse-resize}.ne{right:-7px;top:-7px;cursor:nesw-resize}.sw{left:-7px;bottom:-7px;cursor:nesw-resize}.se{right:-7px;bottom:-7px;cursor:nwse-resize}.rotate{left:50%;top:-24px;width:18px;height:6px;transform:translateX(-50%);cursor:grab;border-radius:0;background:currentColor!important}.fixed .rotate{color:#00e5ff}.moving .rotate{color:#ffb300}.garageFixed .rotate{color:#76ff03}.garageMoving .rotate{color:#e040fb}.garage2Fixed .rotate{color:#40c4ff}.garage2Moving .rotate{color:#ff4081}.fixedTxt{color:#00e5ff}.movingTxt{color:#ffb300}.verticalFixedTxt{color:#76ff03}.verticalMovingTxt{color:#e040fb}.vertical2FixedTxt{color:#40c4ff}.vertical2MovingTxt{color:#ff4081}.personTxt{color:#b388ff}.statusline{font-size:.96rem;margin:3px 0;overflow-wrap:anywhere}@media(max-width:600px){body{padding:8px}.row button{flex:1 1 44%}.panel{padding:10px}.grid{grid-template-columns:1fr}.row label{width:100%}.row input{width:100%}}
</style></head><body><main>
<div class="panel"><div class="grid"><div><strong>Kamera:</strong> <code id="camera">-</code></div><div><strong>Kalibrierzugriff:</strong> <span id="uitime">-</span></div><div><strong>Pause:</strong> <span id="pause">-</span></div><div><strong>Ansicht:</strong> <span id="viewName">Normalbild</span></div></div></div>
<div class="row"><button id="reload">Aktuelles Bild laden</button><button id="edge" class="secondary">Tür-Kantenansicht</button><button id="gEdgeTop" class="secondary" style="display:none">Garage 1 Kantenansicht</button><button id="g2EdgeTop" class="secondary" style="display:none">Garage 2 Kantenansicht</button><button id="personToggle" class="secondary">Personen-Bildbereich</button></div><div id="msg" aria-live="polite"></div>
<div id="stage"><img id="cam" alt="Aktuelles Kamerabild"><div id="fixedRoi" class="roi fixed"><span class="label">ZARGE</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span><span class="handle rotate" data-handle="rotate"></span></div><div id="movingRoi" class="roi moving"><span class="label">TÜR</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span><span class="handle rotate" data-handle="rotate"></span></div><div id="gFixedRoi" class="roi garageFixed" style="display:none"><span class="label">V-FEST</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span><span class="handle rotate" data-handle="rotate"></span></div><div id="gMovingRoi" class="roi garageMoving" style="display:none"><span class="label">V-BEWEGT</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span><span class="handle rotate" data-handle="rotate"></span></div><div id="g2FixedRoi" class="roi garage2Fixed" style="display:none"><span class="label">G2-FEST</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span><span class="handle rotate" data-handle="rotate"></span></div><div id="g2MovingRoi" class="roi garage2Moving" style="display:none"><span class="label">G2-BEWEGT</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span><span class="handle rotate" data-handle="rotate"></span></div><div id="personRoi" class="roi personArea" style="display:none"><span class="label">PERSON / POST</span><span class="handle nw" data-handle="nw"></span><span class="handle ne" data-handle="ne"></span><span class="handle sw" data-handle="sw"></span><span class="handle se" data-handle="se"></span></div></div>
<div class="hint">ROI verschieben: im Rechteck ziehen · Größe: direkt an den Ecken ziehen; die Eckgriffe bleiben unsichtbar. Tür- und Vertikal-ROI können zusätzlich am kleinen Strich oberhalb um ±45° gedreht werden.</div>
<div class="panel"><h3>Haustür – horizontale Messung</h3><div class="row"><label>Name Tür <input id="doorName"></label><label>Entity-ID Tür <input id="doorEntity"></label></div><div class="grid"><div><strong class="fixedTxt">Zarge-ROI:</strong> <code id="fixedCoords">-</code></div><div><strong class="movingTxt">Tür-ROI:</strong> <code id="movingCoords">-</code></div><div><strong>Kalibriert:</strong> <span id="calibrated">-</span></div><div><strong>Türstatus:</strong> <span id="doorstate">-</span></div><div><strong>Kantenpositionen:</strong> <span id="edges">-</span></div><div><strong>Verschiebung:</strong> <span id="score">-</span></div><div><strong>Kantenabstand:</strong> <span id="gap">-</span></div><div><strong>Kantenqualität:</strong> <span id="quality">-</span></div><div><strong>Kanten-Tracking:</strong> <span id="tracking">-</span></div></div><div class="row"><button id="save" class="secondary">Beide ROI speichern</button><button id="calibrate">Tür geschlossen kalibrieren</button><button id="check" class="secondary">Jetzt prüfen</button></div></div>
<div id="garagePanel" class="panel" style="display:none"><h3>Vertikale Zusatzmessung</h3><div class="row"><label>Name <input id="verticalName"></label><label>Entity-ID <input id="verticalEntity"></label></div><div class="grid"><div><strong class="verticalFixedTxt">Fest-ROI:</strong> <code id="gFixedCoords">-</code></div><div><strong class="verticalMovingTxt">Bewegt-ROI:</strong> <code id="gMovingCoords">-</code></div><div><strong>Kalibriert:</strong> <span id="gCalibrated">-</span></div><div><strong>Status:</strong> <span id="gDoorState">-</span></div><div><strong>Verschiebung:</strong> <span id="gShift">-</span></div><div><strong>Kantenabstand:</strong> <span id="gGap">-</span></div><div><strong>Kantenqualität:</strong> <span id="gQuality">-</span></div><div><strong>Kanten-Tracking:</strong> <span id="gTracking">-</span></div><div><strong>Letzte Prüfung:</strong> <span id="gLast">-</span></div></div><div id="gError" class="statusline"></div><div class="row"><button id="gSave" class="secondary">Vertikale ROI speichern</button><button id="gCal">Geschlossen kalibrieren</button><button id="gCheck" class="secondary">Jetzt prüfen</button><button id="gEdge" class="secondary">Vertikale Kantenansicht</button></div></div>

<div id="garage2Panel" class="panel" style="display:none"><h3>Vertikale Zusatzmessung – Garagentor 2</h3><div class="row"><label>Name <input id="vertical2Name"></label><label>Entity-ID <input id="vertical2Entity"></label></div><div class="grid"><div><strong class="vertical2FixedTxt">Fest-ROI:</strong> <code id="g2FixedCoords">-</code></div><div><strong class="vertical2MovingTxt">Bewegt-ROI:</strong> <code id="g2MovingCoords">-</code></div><div><strong>Kalibriert:</strong> <span id="g2Calibrated">-</span></div><div><strong>Status:</strong> <span id="g2DoorState">-</span></div><div><strong>Verschiebung:</strong> <span id="g2Shift">-</span></div><div><strong>Kantenabstand:</strong> <span id="g2Gap">-</span></div><div><strong>Kantenqualität:</strong> <span id="g2Quality">-</span></div><div><strong>Kanten-Tracking:</strong> <span id="g2Tracking">-</span></div><div><strong>Letzte Prüfung:</strong> <span id="g2Last">-</span></div></div><div id="g2Error" class="statusline"></div><div class="row"><button id="g2Save" class="secondary">Garage-2-ROI speichern</button><button id="g2Cal">Geschlossen kalibrieren</button><button id="g2Check" class="secondary">Jetzt prüfen</button><button id="g2Edge" class="secondary">Garage-2-Kantenansicht</button></div></div>

<div class="panel"><h3>Personen-/Postboten-Bildbereich</h3><div class="statusline">Nur dieser Bildbereich wird bei den drei Motion-JPEGs an YOLO übergeben. Er ersetzt das bisher fest codierte Fenster 25–75 % / 10–90 %.</div><div><strong class="personTxt">Bildbereich:</strong> <code id="personCoords">-</code></div><div class="row"><button id="personShow" class="secondary">Bildbereich einblenden</button><button id="personSave">Bildbereich speichern</button></div></div>
</main><script>(()=>{
const $=id=>document.getElementById(id),stage=$('stage'),img=$('cam'),msg=$('msg');const boxes={fixed:$('fixedRoi'),moving:$('movingRoi'),gfixed:$('gFixedRoi'),gmoving:$('gMovingRoi'),g2fixed:$('g2FixedRoi'),g2moving:$('g2MovingRoi'),person:$('personRoi')};
let rois={fixed:{cx:.714,cy:.5,w:.028,h:.6,angle:0},moving:{cx:.746,cy:.5,w:.028,h:.6,angle:0},gfixed:{cx:.45,cy:.35,w:.55,h:.035,angle:0},gmoving:{cx:.45,cy:.55,w:.55,h:.035,angle:0},g2fixed:{cx:.45,cy:.35,w:.55,h:.035,angle:0},g2moving:{cx:.45,cy:.55,w:.55,h:.035,angle:0},person:{cx:.5,cy:.5,w:.5,h:.8}},drag=null,viewMode='normal',verticalEnabled=false,vertical2Enabled=false,personVisible=false,uiRemaining=0,uiTimer=null;
const basePath=window.location.pathname.endsWith('/')?window.location.pathname:(window.location.pathname+'/'),endpoint=n=>basePath+'api/'+n,clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function renderUiTime(){const sec=Math.max(0,Math.ceil(uiRemaining)),m=Math.floor(sec/60),ss=String(sec%60).padStart(2,'0');$('uitime').textContent=sec>0?`${m}:${ss} min aktiv`:'gesperrt'}function startUiTimer(seconds){uiRemaining=Math.max(0,Number(seconds)||0);renderUiTime();if(uiTimer)clearInterval(uiTimer);uiTimer=setInterval(()=>{uiRemaining=Math.max(0,uiRemaining-1);renderUiTime()},1000)}
function coordText(r,rot=true){return `Mitte ${r.cx.toFixed(3)}/${r.cy.toFixed(3)} · Größe ${r.w.toFixed(3)}×${r.h.toFixed(3)}${rot?' · '+Number(r.angle||0).toFixed(1)+'°':''}`}
function overlays(){const normal=viewMode==='normal';boxes.fixed.style.display=normal?'block':'none';boxes.moving.style.display=normal?'block':'none';boxes.gfixed.style.display=(normal&&verticalEnabled)?'block':'none';boxes.gmoving.style.display=(normal&&verticalEnabled)?'block':'none';boxes.g2fixed.style.display=(normal&&vertical2Enabled)?'block':'none';boxes.g2moving.style.display=(normal&&vertical2Enabled)?'block':'none';boxes.person.style.display=(normal&&personVisible)?'block':'none';$('viewName').textContent=viewMode==='normal'?'Normalbild':viewMode==='door-edge'?'Tür-Kantenansicht':viewMode==='vertical-edge'?'Garage 1 Kantenansicht':'Garage 2 Kantenansicht';$('edge').classList.toggle('active',viewMode==='door-edge');$('gEdge').classList.toggle('active',viewMode==='vertical-edge');$('gEdgeTop').classList.toggle('active',viewMode==='vertical-edge');$('g2Edge').classList.toggle('active',viewMode==='vertical2-edge');$('g2EdgeTop').classList.toggle('active',viewMode==='vertical2-edge')}
function render(){const W=stage.clientWidth,H=stage.clientHeight;if(!W||!H)return;for(const n of ['fixed','moving','gfixed','gmoving','g2fixed','g2moving','person']){const r=rois[n],b=boxes[n];b.style.left=(r.cx*100)+'%';b.style.top=(r.cy*100)+'%';b.style.width=(r.w*100)+'%';b.style.height=(r.h*100)+'%';b.style.transform=n==='person'?'translate(-50%,-50%)':`translate(-50%,-50%) rotate(${r.angle}deg)`}$('fixedCoords').textContent=coordText(rois.fixed);$('movingCoords').textContent=coordText(rois.moving);$('gFixedCoords').textContent=coordText(rois.gfixed);$('gMovingCoords').textContent=coordText(rois.gmoving);$('g2FixedCoords').textContent=coordText(rois.g2fixed);$('g2MovingCoords').textContent=coordText(rois.g2moving);$('personCoords').textContent=coordText(rois.person,false);overlays()}
function stagePoint(ev){const q=stage.getBoundingClientRect();return{x:ev.clientX-q.left,y:ev.clientY-q.top,W:q.width,H:q.height}}function begin(ev,name){if(viewMode!=='normal')return;ev.preventDefault();const p=stagePoint(ev),r=rois[name],handle=ev.target.dataset.handle||'move';drag={name,handle,start:p,startR:{...r}};ev.currentTarget.setPointerCapture?.(ev.pointerId)}for(const n of Object.keys(boxes))boxes[n].addEventListener('pointerdown',ev=>begin(ev,n));
window.addEventListener('pointermove',ev=>{if(!drag)return;const p=stagePoint(ev),r=rois[drag.name],s=drag.startR,W=p.W,H=p.H;if(drag.handle==='rotate'&&drag.name!=='person'){const cx=s.cx*W,cy=s.cy*H;let a=Math.atan2(p.y-cy,p.x-cx)*180/Math.PI+90;while(a>180)a-=360;while(a<-180)a+=360;r.angle=clamp(a,-45,45)}else if(drag.handle==='move'){r.cx=clamp(s.cx+(p.x-drag.start.x)/W,s.w/2,1-s.w/2);r.cy=clamp(s.cy+(p.y-drag.start.y)/H,s.h/2,1-s.h/2)}else{const a=(drag.name==='person'?0:s.angle)*Math.PI/180,dx=p.x-drag.start.x,dy=p.y-drag.start.y;const lx=dx*Math.cos(a)+dy*Math.sin(a),ly=-dx*Math.sin(a)+dy*Math.cos(a);const sx=drag.handle.includes('e')?1:-1,sy=drag.handle.includes('s')?1:-1;r.w=clamp(s.w+2*sx*lx/W,.01,.98);r.h=clamp(s.h+2*sy*ly/H,.01,.98);r.cx=clamp(s.cx,r.w/2,1-r.w/2);r.cy=clamp(s.cy,r.h/2,1-r.h/2)}render()});window.addEventListener('pointerup',()=>drag=null);window.addEventListener('pointercancel',()=>drag=null);
async function jsonFetch(url,opt={}){const r=await fetch(url,opt),j=await r.json().catch(()=>({}));if(!r.ok)throw new Error(j.error||('HTTP '+r.status));if(j.calibration_ui_remaining_seconds!==undefined)startUiTimer(j.calibration_ui_remaining_seconds);return j}
async function loadStatus(){const s=await jsonFetch(endpoint('status'));if(s.rois){rois.fixed=s.rois.fixed;rois.moving=s.rois.moving}if(s.vertical_rois){rois.gfixed=s.vertical_rois.fixed;rois.gmoving=s.vertical_rois.moving}if(s.vertical2_rois){rois.g2fixed=s.vertical2_rois.fixed;rois.g2moving=s.vertical2_rois.moving}if(s.person_roi)rois.person=s.person_roi;verticalEnabled=!!s.vertical_enabled;vertical2Enabled=!!s.vertical2_enabled;$('garagePanel').style.display=verticalEnabled?'block':'none';$('gEdgeTop').style.display=verticalEnabled?'inline-block':'none';$('garage2Panel').style.display=vertical2Enabled?'block':'none';$('g2EdgeTop').style.display=vertical2Enabled?'inline-block':'none';$('doorName').value=s.door_name||'';$('doorEntity').value=s.door_entity_id||'';$('verticalName').value=s.vertical_name||'';$('verticalEntity').value=s.vertical_entity_id||'';$('vertical2Name').value=s.vertical2_name||'';$('vertical2Entity').value=s.vertical2_entity_id||'';$('camera').textContent=s.camera_entity;$('calibrated').textContent=s.calibrated?'ja':'nein';$('doorstate').textContent=s.door_open===true?'OFFEN':(s.door_open===false?'geschlossen':'-');$('edges').textContent=(s.last_fixed_x==null||s.last_moving_x==null)?'-':`Zarge ${Number(s.last_fixed_x).toFixed(2)} px · Tür ${Number(s.last_moving_x).toFixed(2)} px`;$('score').textContent=s.last_shift_px==null?'-':`${Number(s.last_shift_px).toFixed(2)} px`;$('gap').textContent=s.last_gap_px==null?'-':`${Number(s.last_gap_px).toFixed(2)} px / Ref ${s.reference_gap_px==null?'-':Number(s.reference_gap_px).toFixed(2)+' px'}`;$('quality').textContent=s.edge_quality==null?'-':Number(s.edge_quality).toFixed(2);$('tracking').textContent=(s.fixed_tracked==null||s.moving_tracked==null)?'-':((s.fixed_tracked&&s.moving_tracked)?'OK':('KANTE VERLOREN'+(s.tracking_reason?' · '+s.tracking_reason:'')));$('pause').textContent=`${Number(s.pause_remaining_seconds||0).toFixed(0)} s`;$('gCalibrated').textContent=s.vertical_calibrated?'ja':'nein';$('gDoorState').textContent=s.vertical_open===true?'OFFEN':s.vertical_open===false?'geschlossen':'-';$('gShift').textContent=s.vertical_shift_px==null?'-':Number(s.vertical_shift_px).toFixed(2)+' px';$('gGap').textContent=s.vertical_gap_px==null?'-':`${Number(s.vertical_gap_px).toFixed(2)} px / Ref ${s.vertical_reference_gap_px==null?'-':Number(s.vertical_reference_gap_px).toFixed(2)+' px'}`;$('gQuality').textContent=s.vertical_quality==null?'-':Number(s.vertical_quality).toFixed(2);$('gTracking').textContent=(s.vertical_fixed_tracked==null||s.vertical_moving_tracked==null)?'-':((s.vertical_fixed_tracked&&s.vertical_moving_tracked)?'OK':('KANTE VERLOREN'+(s.vertical_tracking_reason?' · '+s.vertical_tracking_reason:'')));$('gLast').textContent=s.vertical_last_check||'-';$('gError').textContent=s.vertical_last_error?('Fehler: '+s.vertical_last_error):'';$('g2Calibrated').textContent=s.vertical2_calibrated?'ja':'nein';$('g2DoorState').textContent=s.vertical2_open===true?'OFFEN':s.vertical2_open===false?'geschlossen':'-';$('g2Shift').textContent=s.vertical2_shift_px==null?'-':Number(s.vertical2_shift_px).toFixed(2)+' px';$('g2Gap').textContent=s.vertical2_gap_px==null?'-':`${Number(s.vertical2_gap_px).toFixed(2)} px / Ref ${s.vertical2_reference_gap_px==null?'-':Number(s.vertical2_reference_gap_px).toFixed(2)+' px'}`;$('g2Quality').textContent=s.vertical2_quality==null?'-':Number(s.vertical2_quality).toFixed(2);$('g2Tracking').textContent=(s.vertical2_fixed_tracked==null||s.vertical2_moving_tracked==null)?'-':((s.vertical2_fixed_tracked&&s.vertical2_moving_tracked)?'OK':('KANTE VERLOREN'+(s.vertical2_tracking_reason?' · '+s.vertical2_tracking_reason:'')));$('g2Last').textContent=s.vertical2_last_check||'-';$('g2Error').textContent=s.vertical2_last_error?('Fehler: '+s.vertical2_last_error):'';if(s.last_error)msg.textContent='Letzter Fehler: '+s.last_error;render()}
function imageUrl(){const q=encodeURIComponent(JSON.stringify({fixed:rois.fixed,moving:rois.moving})),vq=encodeURIComponent(JSON.stringify({fixed:rois.gfixed,moving:rois.gmoving})),v2q=encodeURIComponent(JSON.stringify({fixed:rois.g2fixed,moving:rois.g2moving}));if(viewMode==='door-edge')return endpoint('edge_image')+'?t='+Date.now()+'&rois='+q;if(viewMode==='vertical-edge')return endpoint('vertical_edge_image')+'?t='+Date.now()+'&rois='+vq;if(viewMode==='vertical2-edge')return endpoint('vertical2_edge_image')+'?t='+Date.now()+'&rois='+v2q;return endpoint('image')+'?t='+Date.now()}function reloadImage(){img.src=imageUrl()}
$('reload').addEventListener('click',()=>{viewMode='normal';overlays();reloadImage()});$('edge').addEventListener('click',()=>{viewMode=viewMode==='door-edge'?'normal':'door-edge';overlays();reloadImage()});function toggleVerticalEdge(){if(!verticalEnabled)return;viewMode=viewMode==='vertical-edge'?'normal':'vertical-edge';overlays();reloadImage()}$('gEdge').addEventListener('click',toggleVerticalEdge);$('gEdgeTop').addEventListener('click',toggleVerticalEdge);function toggleVertical2Edge(){if(!vertical2Enabled)return;viewMode=viewMode==='vertical2-edge'?'normal':'vertical2-edge';overlays();reloadImage()}$('g2Edge').addEventListener('click',toggleVertical2Edge);$('g2EdgeTop').addEventListener('click',toggleVertical2Edge);
function togglePerson(){viewMode='normal';personVisible=!personVisible;$('personToggle').classList.toggle('active',personVisible);$('personShow').classList.toggle('active',personVisible);$('personToggle').textContent=personVisible?'Personen-Bildbereich ausblenden':'Personen-Bildbereich';$('personShow').textContent=personVisible?'Bildbereich ausblenden':'Bildbereich einblenden';overlays();reloadImage()}$('personToggle').addEventListener('click',togglePerson);$('personShow').addEventListener('click',togglePerson);
$('save').addEventListener('click',async()=>{try{await jsonFetch(endpoint('roi'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fixed:rois.fixed,moving:rois.moving})});msg.textContent='Beide drehbaren Tür-ROI gespeichert. Bitte Tür geschlossen neu kalibrieren.';await loadStatus();reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('calibrate').addEventListener('click',async()=>{try{await jsonFetch(endpoint('calibrate'),{method:'POST'});msg.textContent='Geschlossene Tür wurde als Referenz gespeichert.';await loadStatus();reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('check').addEventListener('click',async()=>{try{const s=await jsonFetch(endpoint('check'),{method:'POST'});msg.textContent='Prüfung: '+(s.door_open?'OFFEN':'geschlossen')+' · Verschiebung '+Number(s.shift_px).toFixed(2)+' px';await loadStatus();if(viewMode==='door-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});
$('gSave').addEventListener('click',async()=>{try{await jsonFetch(endpoint('vertical_roi'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fixed:rois.gfixed,moving:rois.gmoving})});msg.textContent='Vertikale ROI gespeichert. Bitte neu kalibrieren.';await loadStatus();if(viewMode==='vertical-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('gCal').addEventListener('click',async()=>{try{await jsonFetch(endpoint('vertical_calibrate'),{method:'POST'});msg.textContent='Vertikale Referenz kalibriert.';await loadStatus();if(viewMode==='vertical-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('gCheck').addEventListener('click',async()=>{try{const r=await jsonFetch(endpoint('vertical_check'),{method:'POST'});msg.textContent='Vertikale Prüfung: '+(r.open?'OFFEN':'geschlossen')+' · Verschiebung '+Number(r.shift_px).toFixed(2)+' px';await loadStatus();if(viewMode==='vertical-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});
$('g2Save').addEventListener('click',async()=>{try{await jsonFetch(endpoint('vertical2_roi'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fixed:rois.g2fixed,moving:rois.g2moving})});msg.textContent='Garage-2-ROI gespeichert. Bitte neu kalibrieren.';await loadStatus();if(viewMode==='vertical2-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('g2Cal').addEventListener('click',async()=>{try{await jsonFetch(endpoint('vertical2_calibrate'),{method:'POST'});msg.textContent='Garage 2 Referenz kalibriert.';await loadStatus();if(viewMode==='vertical2-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('g2Check').addEventListener('click',async()=>{try{const r=await jsonFetch(endpoint('vertical2_check'),{method:'POST'});msg.textContent='Garage 2 Prüfung: '+(r.open?'OFFEN':'geschlossen')+' · Verschiebung '+Number(r.shift_px).toFixed(2)+' px';await loadStatus();if(viewMode==='vertical2-edge')reloadImage()}catch(e){msg.textContent='Fehler: '+e.message}});$('personSave').addEventListener('click',async()=>{try{const r=await jsonFetch(endpoint('person_roi'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rois.person)});rois.person=r.person_roi||rois.person;msg.textContent='Personen-/Postboten-Bildbereich gespeichert. Er gilt ab dem nächsten 3er-Batch.';render()}catch(e){msg.textContent='Fehler: '+e.message}});
img.addEventListener('load',render);img.addEventListener('error',()=>{msg.textContent='Bild konnte nicht geladen werden. Bitte Ansicht wechseln oder erneut laden.'});window.addEventListener('resize',render);loadStatus().then(reloadImage).catch(e=>msg.textContent='Fehler: '+e.message)
})();</script></body></html>'''


class DoorCalibrationHandler(BaseHTTPRequestHandler):
    server_version = "SmartifyPersonDetectionUI/1.6.2"

    def log_message(self, fmt, *args):
        print(
            "Haustuer-UI:",
            fmt % args
        )

    def _path(self):
        return urlparse(self.path).path.rstrip("/")

    def _ingress_only(self):
        client_ip = self.client_address[0]
        if client_ip == INGRESS_ALLOWED_IP:
            return True

        print(
            f"Haustuer-UI: Zugriff von {client_ip} blockiert "
            f"(erlaubt nur {INGRESS_ALLOWED_IP} via Home Assistant Ingress)."
        )
        self._json(
            {"error": "Zugriff nur ueber Home Assistant Ingress erlaubt."},
            403
        )
        return False

    def _require_active_ui(self):
        if calibration_ui_is_active():
            return True

        self._json(
            {
                "error": (
                    "Kalibrierzugriff abgelaufen. "
                    "Bitte 'Weboberflaeche oeffnen' erneut aufrufen."
                )
            },
            403
        )
        return False

    def _json(self, data, status_code=200):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _body_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        return json.loads(
            self.rfile.read(length).decode("utf-8")
        )

    def do_GET(self):
        if not self._ingress_only():
            return

        path = self._path()

        if path.endswith("/api/status") or path == "/api/status":
            if not self._require_active_ui():
                return
            remaining = max(
                0.0,
                door_pause_until - time.monotonic()
            )

            self._json(
                {
                    "camera_entity": DOOR_CAMERA_ENTITY,
                    "enabled": DOOR_ENABLED,
                    "door_name": DOOR_NAME, "door_entity_id": DOOR_ENTITY_ID,
                    "vertical_enabled": VERTICAL_ENABLED, "vertical_name": VERTICAL_NAME, "vertical_entity_id": VERTICAL_ENTITY_ID,
                    "vertical_rois": {"fixed": dict(vertical_rois["fixed"]), "moving": dict(vertical_rois["moving"])},
                    "vertical_open": vertical_is_open,
                    "vertical_shift_px": vertical_last_shift_px,
                    "vertical_gap_px": vertical_last_gap_px,
                    "vertical_reference_gap_px": vertical_reference_gap_px,
                    "vertical_quality": vertical_last_quality,
                    "vertical_fixed_tracked": vertical_fixed_tracked,
                    "vertical_moving_tracked": vertical_moving_tracked,
                    "vertical_tracking_reason": vertical_tracking_reason,
                    "vertical_last_check": vertical_last_check,
                    "vertical_last_error": vertical_last_error,
                    "vertical_calibrated": VERTICAL_EDGE_REFERENCE.exists(),
                    "vertical2_enabled": VERTICAL2_ENABLED, "vertical2_name": VERTICAL2_NAME, "vertical2_entity_id": VERTICAL2_ENTITY_ID,
                    "vertical2_rois": {"fixed": dict(vertical2_rois["fixed"]), "moving": dict(vertical2_rois["moving"])},
                    "vertical2_open": vertical2_is_open,
                    "vertical2_shift_px": vertical2_last_shift_px,
                    "vertical2_gap_px": vertical2_last_gap_px,
                    "vertical2_reference_gap_px": vertical2_reference_gap_px,
                    "vertical2_quality": vertical2_last_quality,
                    "vertical2_fixed_tracked": vertical2_fixed_tracked,
                    "vertical2_moving_tracked": vertical2_moving_tracked,
                    "vertical2_tracking_reason": vertical2_tracking_reason,
                    "vertical2_last_check": vertical2_last_check,
                    "vertical2_last_error": vertical2_last_error,
                    "vertical2_calibrated": VERTICAL2_EDGE_REFERENCE.exists(),
                    "person_roi": dict(person_roi),
                    "rois": {"fixed": dict(door_rois["fixed"]), "moving": dict(door_rois["moving"])},
                    "calibrated": DOOR_EDGE_REFERENCE.exists(),
                    "door_open": door_is_open,
                    "last_score": door_last_score,
                    "last_shift_px": door_last_shift_px,
                    "last_fixed_x": door_last_fixed_x,
                    "last_moving_x": door_last_moving_x,
                    "last_gap_px": door_last_gap_px,
                    "reference_gap_px": door_reference_gap_px,
                    "edge_quality": door_last_edge_quality,
                    "fixed_tracked": door_fixed_tracked,
                    "moving_tracked": door_moving_tracked,
                    "tracking_reason": door_tracking_reason,
                    "tracking_window_px": DOOR_EDGE_TRACK_WINDOW_PX,
                    "last_check": door_last_check,
                    "last_error": door_last_error,
                    "open_shift_pixels": DOOR_OPEN_SHIFT_PX,
                    "close_shift_pixels": DOOR_CLOSE_SHIFT_PX,
                    "check_interval_seconds": DOOR_CHECK_INTERVAL,
                    "pause_after_motion_seconds": DOOR_PAUSE_AFTER_MOTION,
                    "pause_remaining_seconds": remaining,
                    "calibration_ui_minutes": DOOR_CALIBRATION_UI_MINUTES,
                    "calibration_ui_remaining_seconds": calibration_ui_remaining()
                }
            )
            return

        if path.endswith("/api/edge_image") or path == "/api/edge_image":
            if not self._require_active_ui():
                return
            try:
                _, image = camera_snapshot()
                override = None
                try:
                    query = parse_qs(urlparse(self.path).query)
                    raw = query.get("rois", [None])[0]
                    if raw:
                        candidate = json.loads(raw)
                        if isinstance(candidate, dict) and "fixed" in candidate and "moving" in candidate:
                            override = candidate
                except Exception:
                    override = None
                edge_view, _ = render_edge_view(image, rois_override=override)
                ok, encoded = cv2.imencode(".jpg", edge_view, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
                if not ok:
                    raise RuntimeError("Kantenansicht konnte nicht als JPEG erzeugt werden.")
                data = encoded.tobytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._json({"error": str(e)}, 500)
            return

        if path.endswith("/api/vertical_edge_image") or path == "/api/vertical_edge_image":
            if not self._require_active_ui(): return
            try:
                _,image=camera_snapshot(); override=None; raw=parse_qs(urlparse(self.path).query).get("rois",[None])[0]
                if raw: override=json.loads(raw)
                view,_=render_vertical_edge_view(image,override); ok,enc=cv2.imencode(".jpg",view,[int(cv2.IMWRITE_JPEG_QUALITY),90])
                if not ok: raise RuntimeError("Vertikale Kantenansicht fehlgeschlagen.")
                data=enc.tobytes(); self.send_response(200); self.send_header("Content-Type","image/jpeg"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
            except Exception as e: self._json({"error":str(e)},500)
            return

        if path.endswith("/api/vertical2_edge_image") or path == "/api/vertical2_edge_image":
            if not self._require_active_ui(): return
            try:
                _,image=camera_snapshot(); override=None; raw=parse_qs(urlparse(self.path).query).get("rois",[None])[0]
                if raw: override=json.loads(raw)
                view,_=render_vertical2_edge_view(image,override); ok,enc=cv2.imencode(".jpg",view,[int(cv2.IMWRITE_JPEG_QUALITY),90])
                if not ok: raise RuntimeError("Garage-2-Kantenansicht fehlgeschlagen.")
                data=enc.tobytes(); self.send_response(200); self.send_header("Content-Type","image/jpeg"); self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
            except Exception as e: self._json({"error":str(e)},500)
            return

        if path.endswith("/api/image") or path == "/api/image":
            if not self._require_active_ui():
                return
            try:
                data, _ = camera_snapshot()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self._json(
                    {"error": str(e)},
                    500
                )
            return

        # Nur eine echte Seitennavigation schaltet die UI frei. API-, Bild-
        # oder sonstige Hintergrundrequests duerfen den Timer nicht starten.
        accept = self.headers.get("Accept", "")
        if "text/html" not in accept.lower():
            self._json({"error": "Nicht gefunden."}, 404)
            return

        activate_calibration_ui()
        print(
            f"Haustuer-UI: Kalibrierzugriff fuer "
            f"{DOOR_CALIBRATION_UI_MINUTES} Minuten freigeschaltet."
        )

        html = DOOR_UI_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_POST(self):
        if not self._ingress_only():
            return
        if not self._require_active_ui():
            return

        # Speichern/Kalibrieren/Jetzt pruefen gelten als aktive Bedienung und
        # verlaengern das Freigabefenster wieder auf die volle Dauer.
        touch_calibration_ui()
        path = self._path()

        try:
            if path.endswith("/api/roi") or path == "/api/roi":
                data = self._body_json()

                parsed = {}
                for name in ("fixed", "moving"):
                    source = data[name]
                    cx = float(source["cx"])
                    cy = float(source["cy"])
                    rw = float(source["w"])
                    rh = float(source["h"])
                    angle = float(source.get("angle", 0.0))
                    if not (
                        0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0
                        and 0.008 <= rw <= 0.95 and 0.02 <= rh <= 0.95
                        and -45.0 <= angle <= 45.0
                    ):
                        raise ValueError(f"ROI-Geometrie fuer {name} ist ungueltig.")
                    parsed[name] = {"cx": cx, "cy": cy, "w": rw, "h": rh, "angle": angle}


                with door_config_lock:
                    door_rois["fixed"] = parsed["fixed"]
                    door_rois["moving"] = parsed["moving"]

                save_door_config()

                # Eine alte Referenz gehoert zu einer anderen ROI und
                # darf deshalb nicht weiterverwendet werden.
                if DOOR_REFERENCE.exists():
                    DOOR_REFERENCE.unlink()
                if DOOR_EDGE_REFERENCE.exists():
                    DOOR_EDGE_REFERENCE.unlink()

                publish_door_attributes_only()

                self._json(
                    {
                        "ok": True,
                        "rois": {"fixed": dict(door_rois["fixed"]), "moving": dict(door_rois["moving"])},
                        "needs_calibration": True
                    }
                )
                return

            if path.endswith("/api/calibrate") or path == "/api/calibrate":
                calibrate_closed_door()
                self._json(
                    {
                        "ok": True,
                        "calibrated": True
                    }
                )
                return

            if path.endswith("/api/check") or path == "/api/check":
                result = check_door(force=True)

                if result is None:
                    raise RuntimeError(
                        "Pruefung nicht moeglich. Ist die Tuer bereits kalibriert?"
                    )

                is_open, shift_px = result

                self._json(
                    {
                        "ok": True,
                        "door_open": bool(is_open),
                        "score": float(shift_px),
                        "shift_px": float(shift_px)
                    }
                )
                return

            if path.endswith("/api/person_roi") or path == "/api/person_roi":
                data = self._body_json()
                parsed = _sanitize_person_roi(data)
                with person_roi_lock:
                    person_roi.update(parsed)
                save_person_roi()
                self._json({"ok": True, "person_roi": dict(person_roi)})
                return

            if path.endswith("/api/vertical_roi") or path == "/api/vertical_roi":
                if not VERTICAL_ENABLED: raise RuntimeError("Vertikale Zusatzmessung ist deaktiviert.")
                data=self._body_json(); parsed={}
                for n in ("fixed","moving"):
                    parsed[n]=_sanitize_rotated_roi(data[n],vertical_rois[n])
                with vertical_config_lock: vertical_rois.update(parsed)
                save_vertical_config()
                if VERTICAL_REFERENCE.exists(): VERTICAL_REFERENCE.unlink()
                if VERTICAL_EDGE_REFERENCE.exists(): VERTICAL_EDGE_REFERENCE.unlink()
                self._json({"ok":True,"needs_calibration":True}); return
            if path.endswith("/api/vertical_calibrate") or path == "/api/vertical_calibrate":
                if not VERTICAL_ENABLED: raise RuntimeError("Vertikale Zusatzmessung ist deaktiviert.")
                calibrate_vertical(); self._json({"ok":True}); return
            if path.endswith("/api/vertical_check") or path == "/api/vertical_check":
                r=check_vertical(force=True)
                if r is None: raise RuntimeError("Vertikale Prüfung nicht möglich; zuerst kalibrieren.")
                self._json({"ok":True,"open":bool(r[0]),"shift_px":float(r[1])}); return

            if path.endswith("/api/vertical2_roi") or path == "/api/vertical2_roi":
                if not VERTICAL2_ENABLED: raise RuntimeError("Zweites Garagentor ist deaktiviert.")
                data=self._body_json(); parsed={}
                for n in ("fixed","moving"):
                    parsed[n]=_sanitize_rotated_roi(data[n],vertical2_rois[n])
                with vertical2_config_lock: vertical2_rois.update(parsed)
                save_vertical2_config()
                if VERTICAL2_REFERENCE.exists(): VERTICAL2_REFERENCE.unlink()
                if VERTICAL2_EDGE_REFERENCE.exists(): VERTICAL2_EDGE_REFERENCE.unlink()
                self._json({"ok":True,"needs_calibration":True}); return
            if path.endswith("/api/vertical2_calibrate") or path == "/api/vertical2_calibrate":
                if not VERTICAL2_ENABLED: raise RuntimeError("Zweites Garagentor ist deaktiviert.")
                calibrate_vertical2(); self._json({"ok":True}); return
            if path.endswith("/api/vertical2_check") or path == "/api/vertical2_check":
                r=check_vertical2(force=True)
                if r is None: raise RuntimeError("Garage-2-Prüfung nicht möglich; zuerst kalibrieren.")
                self._json({"ok":True,"open":bool(r[0]),"shift_px":float(r[1])}); return

            self._json(
                {"error": "Unbekannter Endpunkt."},
                404
            )

        except Exception as e:
            self._json(
                {"error": str(e)},
                400
            )


class DoorHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_door_web_ui():
    server = DoorHTTPServer(
        ("0.0.0.0", DOOR_WEB_PORT),
        DoorCalibrationHandler
    )

    thread = threading.Thread(
        target=server.serve_forever,
        name="door-calibration-ui",
        daemon=True
    )

    thread.start()

    print(
        f"Haustuer-Kalibrieroberflaeche auf Port {DOOR_WEB_PORT} gestartet."
    )

    return server


# ---------------------------------------------------------
# MQTT Reset empfangen
# ---------------------------------------------------------

def on_message(client, userdata, msg):

    global post_timer
    global person_timer

    try:
        payload = msg.payload.decode().strip().upper()

    except Exception:
        payload = ""


    if msg.topic == POST_RESET_TOPIC and payload == "RESET":
        print("Post abgeholt: separater Post-Reset empfangen.")
        if post_timer:
            post_timer.cancel()
            post_timer = None
        client.publish(status, "OFF", retain=True)
        print("Post-Sensor auf OFF gesetzt; Person-Sensor bleibt unveraendert.")
        return

    if msg.topic == RESET_TOPIC and payload == "RESET":

        print("Manueller Gesamt-Reset empfangen.")


        if post_timer:
            post_timer.cancel()
            post_timer = None


        if person_timer:
            person_timer.cancel()
            person_timer = None


        client.publish(
            status,
            "OFF",
            retain=True
        )


        client.publish(
            person_status,
            "OFF",
            retain=True
        )


        print(
            "Post- und Person-Sensor auf OFF gesetzt."
        )


c.on_message = on_message


# ---------------------------------------------------------
# MQTT Verbindung
# ---------------------------------------------------------

def connected(
    client,
    userdata,
    flags,
    reason_code,
    properties
):

    print(
        "MQTT verbunden:",
        reason_code
    )


    if reason_code == 0:

        client.publish(
            avail,
            "online",
            retain=True
        )

        discovery()

        publish_counter_attributes()
        publish_door_attributes_only()
        publish_vertical_state()
        publish_vertical2_state()

        client.subscribe(RESET_TOPIC)
        client.subscribe(POST_RESET_TOPIC)

        print(f"Reset-Topics abonniert: {RESET_TOPIC}, {POST_RESET_TOPIC}")

    else:

        print(
            "MQTT-Verbindung nicht erfolgreich."
        )


c.on_connect = connected


# ---------------------------------------------------------
# Post erkannt
# ---------------------------------------------------------

def hit(name, ratio):

    global post_timer


    c.publish(
        status,
        "ON",
        retain=True
    )


    timestamp = (
        datetime
        .now(timezone.utc)
        .astimezone()
        .isoformat(timespec="seconds")
    )


    c.publish(
        last,
        timestamp,
        retain=True
    )


    # Trefferbild mit stabilem Dateinamen sichern, damit es nicht mit
    # dem rotierenden Motion-Ordner verschwindet/ueberschrieben wird.
    src_path = IMG / name
    try:
        shutil.copy2(str(src_path), str(SNAPSHOT_PATH))
        print(f"Treffer-Bild gespeichert: {SNAPSHOT_PATH}")
    except Exception as exc:
        print(f"Konnte Treffer-Bild nicht kopieren: {exc}")

    # Bestehende Semantik des Sensors "Postboten Bild" beibehalten:
    # weiterhin den Original-Dateinamen aus dem Motion-Ordner publizieren.
    c.publish(
        image_topic,
        name,
        retain=True
    )


    c.publish(
        ratio_topic,
        f"{ratio:.3f}",
        retain=True
    )


    if post_timer:
        post_timer.cancel()


    def auto_off():

        global post_timer

        print(
            "Automatischer Post-Reset."
        )

        c.publish(
            status,
            "OFF",
            retain=True
        )

        post_timer = None


    # Explizit abschaltbarer Auto-Reset. Zusätzlich bleibt 0 Sekunden
    # abwärtskompatibel als "deaktiviert" erhalten.
    if POST_AUTO_RESET and ONSECS > 0:
        post_timer = threading.Timer(
            ONSECS,
            auto_off
        )

        post_timer.daemon = True

        post_timer.start()
    else:
        post_timer = None
        print("Post-Auto-Reset deaktiviert.")


# ---------------------------------------------------------
# Person erkannt
# ---------------------------------------------------------

def person_hit(name):

    global person_timer


    c.publish(
        person_status,
        "ON",
        retain=True
    )


    # Letztes Personenbild ebenfalls mit stabilem Dateinamen sichern.
    # Der Original-Dateiname im MQTT-Sensor bleibt aus Kompatibilitaetsgruenden erhalten.
    src_path = IMG / name
    try:
        shutil.copy2(str(src_path), str(PERSON_SNAPSHOT_PATH))
        print(f"Person-Bild gespeichert: {PERSON_SNAPSHOT_PATH}")
    except Exception as exc:
        print(f"Konnte Person-Bild nicht kopieren: {exc}")

    c.publish(
        person_image_topic,
        name,
        retain=True
    )


    print(
        f"Person-Sensor auf ON gesetzt. Bild: {name}"
    )


    if person_timer:
        person_timer.cancel()


    def person_auto_off():

        global person_timer

        c.publish(
            person_status,
            "OFF",
            retain=True
        )

        print(
            "Person-Sensor automatisch auf OFF gesetzt."
        )

        person_timer = None


    # Explizit abschaltbarer Auto-Reset. Zusätzlich bleibt 0 Sekunden
    # abwärtskompatibel als "deaktiviert" erhalten.
    if PERSON_AUTO_RESET and PERSON_ON_SECONDS > 0:
        person_timer = threading.Timer(
            PERSON_ON_SECONDS,
            person_auto_off
        )

        person_timer.daemon = True

        person_timer.start()
    else:
        person_timer = None
        print("Person-Auto-Reset deaktiviert.")


# ---------------------------------------------------------
# Gelbanteil im Oberkörper
# ---------------------------------------------------------

def yellow(crop):

    if crop is None or crop.size == 0:
        return 0.0


    h, w = crop.shape[:2]


    torso = crop[
        int(h * 0.15):int(h * 0.60),
        int(w * 0.15):int(w * 0.85)
    ]


    if torso.size == 0:
        return 0.0


    hsv = cv2.cvtColor(
        torso,
        cv2.COLOR_BGR2HSV
    )


    lower_yellow = np.array(
        [20, 80, 80],
        dtype=np.uint8
    )


    upper_yellow = np.array(
        [38, 255, 255],
        dtype=np.uint8
    )


    mask = cv2.inRange(
        hsv,
        lower_yellow,
        upper_yellow
    )


    ratio = (
        float(np.count_nonzero(mask))
        / float(mask.size)
    )


    return ratio


# ---------------------------------------------------------
# Bild analysieren
#
# Rückgabe:
#
# yellow_found
# person_found
# yellow_ratio
# ---------------------------------------------------------

def analyze(p):

    im = cv2.imread(str(p))


    if im is None:

        print(
            f"Bild kann nicht gelesen werden: {p}"
        )

        return False, False, 0.0


    h, w = im.shape[:2]


    # -----------------------------------------------------
    # Frei waehlbarer Bildbereich fuer Personen/Postboten.
    # -----------------------------------------------------
    with person_roi_lock:
        pr = dict(person_roi)

    x1_roi = int(round(w * (pr["cx"] - pr["w"] / 2.0)))
    x2_roi = int(round(w * (pr["cx"] + pr["w"] / 2.0)))
    y1_roi = int(round(h * (pr["cy"] - pr["h"] / 2.0)))
    y2_roi = int(round(h * (pr["cy"] + pr["h"] / 2.0)))

    x1_roi = max(0, min(w - 1, x1_roi))
    x2_roi = max(x1_roi + 1, min(w, x2_roi))
    y1_roi = max(0, min(h - 1, y1_roi))
    y2_roi = max(y1_roi + 1, min(h, y2_roi))
    roi = im[y1_roi:y2_roi, x1_roi:x2_roi]


    if roi.size == 0:

        print(
            f"ROI ungültig: {p.name}"
        )

        return False, False, 0.0


    best = 0.0
    person_found = False


    for x1, y1, x2, y2, box_conf in detect_persons(roi, CONF_SCAN):

        # Fuer den normalen Person-Sensor bleibt CONF die harte Schwelle.
        # Ein Low-Confidence-Kandidat wird nur dann als echte Person
        # akzeptiert, wenn er spaeter zugleich die starke Gelb-Ausnahme
        # erfuellt und damit als Postbote gilt.
        if box_conf >= CONF:
            person_found = True


        person = roi[
            y1:y2,
            x1:x2
        ]


        q = yellow(
            person
        )


        best = max(
            best,
            q
        )


        print(
            f"Person-Kandidat: conf={box_conf:.3f}, Gelbanteil={q:.3f}"
        )


        if q >= TH and (
            box_conf >= CONF
            or q >= TH * STRONG_YELLOW_FACTOR
        ):
            # Ein Postboten-Treffer ist gleichzeitig eine valide Person,
            # auch wenn die YOLO-Confidence nur ueber CONF_SCAN lag.
            return True, True, q


    return False, person_found, best


# ---------------------------------------------------------
# JPEG-Dateien finden
# ---------------------------------------------------------

def files():

    result = []


    for pattern in (
        "*.jpg",
        "*.jpeg",
        "*.JPG",
        "*.JPEG"
    ):

        result.extend(
            IMG.glob(pattern)
        )


    return sorted(
        result,
        key=lambda p: (
            p.stat().st_mtime_ns,
            p.name
        )
    )


# ---------------------------------------------------------
# Neue / geänderte Bilder
# ---------------------------------------------------------

def get_new_files():

    new_files = []


    for p in files():

        try:

            current_mtime = (
                p.stat().st_mtime_ns
            )


            previous_mtime = (
                processed.get(
                    p.name
                )
            )


            if (
                previous_mtime is None
                or
                current_mtime > previous_mtime
            ):

                new_files.append(
                    p
                )


        except FileNotFoundError:

            continue


    return sorted(
        new_files,
        key=lambda p: (
            p.stat().st_mtime_ns,
            p.name
        )
    )


# ---------------------------------------------------------
# Datei stabil?
# ---------------------------------------------------------

def stable(p):

    try:

        stat1 = p.stat()

        size1 = stat1.st_size
        mtime1 = stat1.st_mtime_ns


        time.sleep(
            0.4
        )


        stat2 = p.stat()

        size2 = stat2.st_size
        mtime2 = stat2.st_mtime_ns


        return (
            size1 > 0
            and
            size1 == size2
            and
            mtime1 == mtime2
        )


    except Exception:

        return False


# ---------------------------------------------------------
# Bildordner prüfen
# ---------------------------------------------------------

if not IMG.exists():

    raise RuntimeError(
        f"Bildordner existiert nicht: {IMG}"
    )


# ---------------------------------------------------------
# Erststart
# ---------------------------------------------------------

if not STATE.exists():

    for p in files():

        if p.name.lower().startswith("rtsp_"):
            continue

        try:

            processed[p.name] = (
                p.stat().st_mtime_ns
            )

        except FileNotFoundError:

            pass


    save_state()


    print(
        f"Erststart: "
        f"{len(processed)} "
        f"vorhandene Bilder als alt markiert."
    )


# ---------------------------------------------------------
# Startinformationen
# ---------------------------------------------------------

print(
    f"Überwache: {IMG}"
)

print(
    f"Ordnerscan alle {SCAN_INTERVAL} Sekunden"
)

print(
    f"MQTT: {HOST}:{PORT}"
)

print(
    f"Reset Topics: Gesamt={RESET_TOPIC}, nur Post={POST_RESET_TOPIC}"
)

print(
    f"Gelb-Schwelle: {TH}"
)

print(
    f"YOLO-Confidence: normal={CONF}, Kandidaten-Scan={CONF_SCAN}, "
    f"Stark-Gelb-Faktor={STRONG_YELLOW_FACTOR}"
)

print(
    f"Treffer-Snapshot: {SNAPSHOT_PATH}"
)

print(
    f"Person-Sensor ON-Zeit: "
    f"{PERSON_ON_SECONDS} Sekunden"
)

print(
    f"Tageszaehler: Personen={person_count_today}, "
    f"Postboten={post_count_today}, Datum={counter_date}, "
    f"Mitternacht-Binary-Reset={RESET_BINARIES_AT_MIDNIGHT}"
)

print(
    f"Haustuer: {'aktiv' if DOOR_ENABLED else 'deaktiviert'}, "
    f"Kamera={DOOR_CAMERA_ENTITY}, "
    f"Intervall={DOOR_CHECK_INTERVAL}s, "
    f"Bewegungspause={DOOR_PAUSE_AFTER_MOTION}s, "
    f"Offen ab={DOOR_OPEN_SHIFT_PX}px, Zu bis={DOOR_CLOSE_SHIFT_PX}px"
)

print(
    f"Garagentor 1: {'aktiv' if VERTICAL_ENABLED else 'deaktiviert'}, Entity={VERTICAL_ENTITY_ID}; "
    f"Garagentor 2: {'aktiv' if VERTICAL2_ENABLED else 'deaktiviert'}, Entity={VERTICAL2_ENTITY_ID}"
)

print(
    f"Haustuer-UI: nur Home-Assistant-Ingress {INGRESS_ALLOWED_IP}, "
    f"Freigabe={DOOR_CALIBRATION_UI_MINUTES} Minuten nach Oeffnen."
)


# ---------------------------------------------------------
# MQTT verbinden
# ---------------------------------------------------------

c.connect(
    HOST,
    PORT,
    60
)

c.loop_start()

start_door_web_ui()

threading.Thread(
    target=door_worker,
    name="door-worker",
    daemon=True
).start()

# ---------------------------------------------------------
# Robuste Batch-Verarbeitung / RTSP-Fallback
# ---------------------------------------------------------

pending_first_seen = {}
rtsp_unhealthy_since = None
rtsp_fallback_active = False


def _mark_processed(paths, reason=None):
    changed = False
    for p in paths:
        if p.name.lower().startswith("rtsp_"):
            pending_first_seen.pop(p.name, None)
            continue
        try:
            processed[p.name] = p.stat().st_mtime_ns
            pending_first_seen.pop(p.name, None)
            changed = True
        except FileNotFoundError:
            pending_first_seen.pop(p.name, None)
    if changed:
        current_names = {p.name for p in files()}
        for name in list(processed):
            if name not in current_names:
                processed.pop(name, None)
        save_state()
    if reason and paths:
        print(reason + ": " + ", ".join(p.name for p in paths))


def _folder_candidates():
    # rtsp_*.jpg werden vom RTSP-Modul selbst ausgewertet und duerfen im
    # automatischen Ordner-Fallback nicht ein zweites Mal zaehlen.
    return [p for p in get_new_files() if not p.name.lower().startswith("rtsp_")]


def process_batch(batch, partial=False):
    if not batch:
        return
    if partial:
        print(
            f"Pruefe Restgruppe nach Timeout ({len(batch)}/{BATCH_SIZE} Bilder):",
            ", ".join(p.name for p in batch)
        )
    else:
        print(f"Pruefe neue {len(batch)}er-Gruppe:", ", ".join(p.name for p in batch))

    yellow_found = None
    person_detected = False
    person_image_name = None

    for p in batch:
        try:
            yellow_ok, person_ok, q = analyze(p)
        except Exception as exc:
            print(f"{p.name}: Analysefehler: {exc}; Datei wird uebersprungen.")
            continue
        print(f"{p.name}: Person={person_ok}, Gelb={q:.3f}, Postbote={yellow_ok}")
        if person_ok:
            person_detected = True
            if person_image_name is None:
                person_image_name = p.name
        if yellow_ok and yellow_found is None:
            yellow_found = (p.name, q)

    if person_detected:
        print("PERSON ERKANNT:", person_image_name)
        count_person()
        person_hit(person_image_name)

    if yellow_found:
        print("POSTBOTEN-KANDIDAT:", yellow_found[0])
        count_post()
        hit(*yellow_found)

    # Pro Erkennungsereignis genau ein Ton. Ein Postbote ist zugleich Person,
    # deshalb hat der speziellere Post-Ton Vorrang.
    if yellow_found:
        play_detection_sound("post")
    elif person_detected:
        play_detection_sound("person")

    _mark_processed(batch)


def process_folder_queue():
    global last_motion_signature
    while True:
        new = _folder_candidates()
        now_mono = time.monotonic()

        new_names = {p.name for p in new}
        for name in list(pending_first_seen):
            if name not in new_names:
                pending_first_seen.pop(name, None)
        for p in new:
            pending_first_seen.setdefault(p.name, now_mono)

        if new:
            newest = new[-1]
            try:
                motion_signature = (newest.name, newest.stat().st_mtime_ns)
            except FileNotFoundError:
                motion_signature = None
            if motion_signature is not None and motion_signature != last_motion_signature:
                last_motion_signature = motion_signature
                pause_door_after_motion()

        print(f"Ordnerscan: {len(new)} neue/geaenderte Bilder gefunden.")
        if not new:
            return

        stable_files = []
        unstable_files = []
        for p in new:
            if stable(p):
                # Stabil reicht nicht: JPEG muss auch wirklich dekodierbar sein.
                try:
                    img = cv2.imread(str(p))
                except Exception:
                    img = None
                if img is None or img.size == 0:
                    unstable_files.append(p)
                else:
                    stable_files.append(p)
            else:
                unstable_files.append(p)

        stale_unstable = [
            p for p in unstable_files
            if now_mono - pending_first_seen.get(p.name, now_mono) >= PARTIAL_BATCH_TIMEOUT_SECONDS
        ]
        if stale_unstable:
            _mark_processed(
                stale_unstable,
                reason=f"Ueberspringe seit mindestens {PARTIAL_BATCH_TIMEOUT_SECONDS:.0f}s instabile/defekte Datei(en)"
            )
            continue

        if len(stable_files) >= BATCH_SIZE:
            process_batch(stable_files[:BATCH_SIZE], partial=False)
            continue

        if stable_files:
            oldest_wait = max(
                now_mono - pending_first_seen.get(p.name, now_mono) for p in stable_files
            )
            if oldest_wait >= PARTIAL_BATCH_TIMEOUT_SECONDS:
                process_batch(stable_files, partial=True)
                continue
            remaining = max(0.0, PARTIAL_BATCH_TIMEOUT_SECONDS - oldest_wait)
            print(
                f"Restgruppe: {len(stable_files)}/{BATCH_SIZE} stabile Bilder; "
                f"Auswertung spaetestens in {remaining:.0f}s, falls kein weiteres Bild kommt."
            )

        if unstable_files:
            oldest_unstable = max(
                now_mono - pending_first_seen.get(p.name, now_mono) for p in unstable_files
            )
            print(
                f"{len(unstable_files)} Bild(er) noch instabil/defekt; "
                f"aeltestes wartet {oldest_unstable:.0f}s."
            )
        return


def _sync_motion_files_known():
    """Aktuelle Nicht-RTSP-Dateien als bekannt halten, ohne state.json aufzublähen."""
    current = {}

    for p in files():
        if p.name.lower().startswith("rtsp_"):
            continue
        try:
            current[p.name] = p.stat().st_mtime_ns
        except FileNotFoundError:
            continue

    changed = False

    # Neue/geänderte Motion-Dateien übernehmen.
    for name, mtime_ns in current.items():
        if processed.get(name) != mtime_ns:
            processed[name] = mtime_ns
            changed = True

    # Gelöschte Motion-Dateien sowie eventuelle alte RTSP-State-Einträge entfernen.
    for name in list(processed):
        if name.lower().startswith("rtsp_") or name not in current:
            processed.pop(name, None)
            pending_first_seen.pop(name, None)
            changed = True

    if changed:
        save_state()


import rtsp_source
RTSP_MODE = rtsp_source.start(globals())

# ---------------------------------------------------------
# Hauptschleife
# ---------------------------------------------------------

while True:
    try:
        check_daily_counter_reset()

        if RTSP_MODE:
            healthy = rtsp_source.stream_ok(max_age=5.0)
            now_mono = time.monotonic()

            if healthy:
                if rtsp_fallback_active:
                    print("RTSP wieder stabil - Ordner-Fallback beendet.")
                rtsp_fallback_active = False
                rtsp_unhealthy_since = None

                # Nur Kamera-Motion-Dateien als bekannt halten. RTSP-Ringpuffer-
                # Dateien werden direkt vom RTSP-Modul verarbeitet und niemals
                # in /data/state.json aufgenommen.
                _sync_motion_files_known()
            else:
                if rtsp_unhealthy_since is None:
                    rtsp_unhealthy_since = now_mono
                    print(
                        f"RTSP aktuell nicht verfuegbar; Ordner-Fallback startet nach "
                        f"{RTSP_FALLBACK_AFTER_SECONDS:.0f}s, falls der Stream nicht zurueckkommt."
                    )

                outage = now_mono - rtsp_unhealthy_since
                if outage >= RTSP_FALLBACK_AFTER_SECONDS:
                    if not rtsp_fallback_active:
                        print(
                            f"RTSP seit {outage:.0f}s ausgefallen - aktiviere automatisch Ordner-Fallback."
                        )
                    rtsp_fallback_active = True
                    process_folder_queue()

        else:
            process_folder_queue()

        time.sleep(SCAN_INTERVAL)

    except Exception as e:
        print("Fehler in Hauptschleife:", e)
        time.sleep(SCAN_INTERVAL)
