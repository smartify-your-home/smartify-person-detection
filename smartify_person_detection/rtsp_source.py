"""RTSP-Quelle mit Ringpuffer fuer den Postbote Detector.



Ablauf:

- Reader-Thread haelt den RTSP-Stream offen und legt Frames als JPEG

  (rtsp_buffer_fps pro Sekunde) in einen Ringpuffer.

- Trigger-Thread fragt die konfigurierten HA-Entities ab (off -> on).

- Bei einem Trigger werden Frames von rtsp_pre_seconds vor bis

  rtsp_post_seconds nach dem Trigger ausgewertet (rtsp_analyze_fps).

- Die ausgewaehlten Frames landen als rtsp_XXX.jpg im image_dir und

  werden mit analyze()/person_hit()/hit() aus app.py ausgewertet.

"""



import json

import os
import re

import threading

import time

from collections import deque
from datetime import datetime

from urllib.parse import quote, urlsplit, urlunsplit

from urllib.request import Request, urlopen



import cv2

import numpy as np



ENABLED = False



_app = None

_buffer = deque()

_buffer_lock = threading.Lock()

_latest_jpeg = None

_last_frame_time = 0.0
_last_trigger_poll_ok = 0.0

_file_index = 0

_orig_camera_snapshot = None





def _opt(key, default):

    return _app["O"].get(key, default)





def _configure(app_globals):

    global _app, ENABLED, URL, URL_MASKED, TRANSPORT, BUFFER_FPS, JPEG_Q

    global PRE, POST, ANALYZE_FPS, TRIGGERS, POLL, REARM_OFF, MAX_FILES, DOOR_USE



    _app = app_globals

    ENABLED = bool(_opt("rtsp_enabled", False))

    if not ENABLED:

        return



    url = str(_opt("rtsp_url", "")).strip()

    user = str(_opt("rtsp_username", "")).strip()

    pw = str(_opt("rtsp_password", ""))

    if not url:

        raise RuntimeError("rtsp_url ist leer.")



    parts = urlsplit(url)

    host = parts.hostname or ""

    port = f":{parts.port}" if parts.port else ""

    if user:

        cred = f"{quote(user, safe='')}:{quote(pw, safe='')}@"

        URL = urlunsplit((parts.scheme, cred + host + port, parts.path, parts.query, parts.fragment))

        URL_MASKED = urlunsplit((parts.scheme, f"{user}:***@{host}{port}", parts.path, parts.query, parts.fragment))

    else:

        URL = url

        URL_MASKED = url



    TRANSPORT = str(_opt("rtsp_transport", "tcp")).strip() or "tcp"

    BUFFER_FPS = max(0.5, float(_opt("rtsp_buffer_fps", 4)))

    JPEG_Q = min(100, max(50, int(_opt("rtsp_jpeg_quality", 92))))

    PRE = max(0.0, float(_opt("rtsp_pre_seconds", 2.0)))

    POST = max(0.5, float(_opt("rtsp_post_seconds", 3.0)))

    ANALYZE_FPS = max(0.5, float(_opt("rtsp_analyze_fps", 2.0)))

    POLL = max(0.2, float(_opt("rtsp_trigger_poll_seconds", 0.5)))

    REARM_OFF = max(0.0, float(_opt("rtsp_rearm_off_seconds", 10)))

    MAX_FILES = max(10, int(_opt("rtsp_max_files", 60)))

    DOOR_USE = bool(_opt("door_use_rtsp", False))

    TRIGGERS = [

        e.strip() for e in str(_opt(

            "rtsp_trigger_entities",

            "binary_sensor.front_door_person,binary_sensor.front_door_fahrzeug"

        )).split(",") if e.strip()

    ]



    # Muss vor dem Oeffnen des Streams gesetzt sein. TCP ist bei

    # schwachem WLAN deutlich robuster (keine verlorenen UDP-Pakete).

    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{TRANSPORT}"





# ---------------------------------------------------------

# Reader: Stream offen halten, Ringpuffer fuellen

# ---------------------------------------------------------



def _reader():

    global _latest_jpeg, _last_frame_time



    keep_seconds = PRE + POST + 2.0

    min_dt = 1.0 / BUFFER_FPS



    while True:

        cap = None

        try:

            print(f"RTSP: verbinde {URL_MASKED} ({TRANSPORT}) ...")

            cap = cv2.VideoCapture(

                URL,

                cv2.CAP_FFMPEG,

                [

                    cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,

                    cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000,

                ],

            )

            if not cap.isOpened():

                raise RuntimeError("Stream konnte nicht geoeffnet werden (URL/Zugangsdaten/RTSP pruefen).")



            print(

                f"RTSP: verbunden, "

                f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))} "

                f"@ {cap.get(cv2.CAP_PROP_FPS):.1f} fps, Puffer {BUFFER_FPS:g} fps / {keep_seconds:g} s"

            )



            next_keep = 0.0

            fails = 0



            while True:

                # grab() fuer JEDEN Frame, sonst laeuft der Stream-Puffer

                # voll und die Bilder hinken hinterher.

                if not cap.grab():

                    fails += 1

                    if fails >= 20:

                        raise RuntimeError("Stream liefert keine Frames mehr.")

                    time.sleep(0.05)

                    continue

                fails = 0



                now = time.monotonic()
                frame_wall_time = time.time()

                if now < next_keep:

                    continue



                ok, frame = cap.retrieve()

                if not ok or frame is None:

                    continue



                ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_Q])

                if not ok:

                    continue



                data = enc.tobytes()

                with _buffer_lock:

                    _buffer.append((now, frame_wall_time, data))

                    while _buffer and _buffer[0][0] < now - keep_seconds:

                        _buffer.popleft()

                    _latest_jpeg = data

                    _last_frame_time = now



                next_keep = now + min_dt



        except Exception as e:

            print(f"RTSP-Fehler: {e} - neuer Versuch in 5 s")

        finally:

            if cap is not None:

                cap.release()



        time.sleep(5)





def stream_ok(max_age=5.0):

    with _buffer_lock:

        return _latest_jpeg is not None and (time.monotonic() - _last_frame_time) < max_age





# ---------------------------------------------------------

# Trigger: HA-Entities abfragen

# ---------------------------------------------------------



def _entity_on(entity):

    req = Request(

        f"http://supervisor/core/api/states/{quote(entity, safe='._-')}",

        headers={"Authorization": f"Bearer {_app['SUPERVISOR_TOKEN']}"},

    )

    with urlopen(req, timeout=3) as r:

        return json.loads(r.read().decode("utf-8")).get("state") == "on"





def _trigger_loop():

    global _last_trigger_poll_ok

    prev = {e: None for e in TRIGGERS}
    last_err = {}

    # Nach einem ausgeloesten Ereignis wird die Erkennung gesperrt.
    # Erst wenn ALLE konfigurierten Trigger-Sensoren fuer REARM_OFF
    # Sekunden durchgehend OFF waren, wird wieder scharf geschaltet.
    armed = True
    all_off_since = None

    while True:

        fired = None
        current = {}
        poll_ok = True

        for e in TRIGGERS:

            try:
                on = _entity_on(e)
                current[e] = on
                _last_trigger_poll_ok = time.monotonic()

                if last_err.pop(e, None):
                    print(f"RTSP-Trigger: {e} wieder abfragbar.")

            except Exception as ex:
                poll_ok = False
                msg = str(ex)

                if last_err.get(e) != msg:
                    print(f"RTSP-Trigger: {e} nicht abfragbar: {msg}")
                    last_err[e] = msg

                continue

            # Nur im scharfen Zustand auf off -> on reagieren.
            # prev None = erster Durchlauf, also kein Trigger beim Start.
            if armed and on and prev[e] is False and fired is None:
                fired = e

            prev[e] = on

        if fired:

            # Sofort sperren, damit ein flatternder Sensor oder eine stehende
            # Person nicht mehrere Ereignisse fuer dieselbe Anwesenheit erzeugt.
            armed = False
            all_off_since = None
            print(
                f"RTSP-Trigger gesperrt: neuer Event erst nachdem alle Trigger "
                f"{REARM_OFF:g}s durchgehend OFF waren."
            )

            try:
                _handle_event(fired, time.monotonic())

            except Exception as ex:
                print(f"RTSP: Fehler bei Ereignisauswertung: {ex}")

            # Die Auswertung kann mehrere Sekunden dauern. Danach den Zustand
            # neu einlesen; im gesperrten Zustand werden Flanken ignoriert.
            prev = {e: None for e in TRIGGERS}
            time.sleep(POLL)
            continue

        if not armed:
            # Nur bei erfolgreicher Abfrage ALLER Trigger kann rearmed werden.
            all_known = poll_ok and len(current) == len(TRIGGERS)
            all_off = all_known and all(not current[e] for e in TRIGGERS)

            if all_off:
                now = time.monotonic()
                if all_off_since is None:
                    all_off_since = now
                elif now - all_off_since >= REARM_OFF:
                    armed = True
                    all_off_since = None
                    # Alle Sensoren sind gerade OFF; so wird die naechste
                    # echte OFF->ON-Flanke sicher erkannt.
                    prev = {e: False for e in TRIGGERS}
                    print(
                        f"RTSP-Trigger wieder scharf: alle Trigger waren "
                        f"mindestens {REARM_OFF:g}s durchgehend OFF."
                    )
            else:
                all_off_since = None

        time.sleep(POLL)


def _rtsp_slot_index(path):
    """Ringpuffer-Slot aus alten und aktuellen RTSP-Dateinamen lesen."""
    m = re.match(r"^rtsp_(\d+)(?:_.*)?\.jpg$", path.name, re.IGNORECASE)
    if not m:
        return None
    try:
        idx = int(m.group(1))
    except ValueError:
        return None
    if idx < 0 or idx >= MAX_FILES:
        return None
    return idx



def _slot_files(idx):
    """Alle Dateien eines Ringpuffer-Slots finden, auch aus älteren Versionen."""
    result = []
    prefix = f"rtsp_{idx:03d}"
    try:
        for path in _app["IMG"].glob(f"{prefix}*.jpg"):
            if _rtsp_slot_index(path) == idx:
                result.append(path)
        for path in _app["IMG"].glob(f"{prefix}*.JPG"):
            if _rtsp_slot_index(path) == idx and path not in result:
                result.append(path)
    except Exception:
        pass
    return result


def _initialize_file_index():
    """Startindex für den RTSP-Datei-Ringpuffer bestimmen.

    Aktuelle Dateinamen sind stabil, z. B.:
      rtsp_027.jpg

    Die echte Aufnahmezeit steckt in der Datei-mtime.
    Ältere Zeitstempel-Dateinamen aus 1.4.6-1.5.0 werden beim Start erkannt
    und pro Slot bereinigt.

    Jeder Index bleibt genau ein Ringpuffer-Slot.
    - Gibt es freie Slots, wird der kleinste freie verwendet.
    - Sind alle Slots belegt, wird der Slot mit dem ältesten Bild gewählt.
    - Falls durch ältere Versionen mehrere Dateien denselben Slot belegen,
      bleibt nur die neueste erhalten.
    """
    global _file_index

    existing = {}

    try:
        candidates = list(_app["IMG"].glob("rtsp_*.jpg"))
        candidates += list(_app["IMG"].glob("rtsp_*.JPG"))
    except Exception as exc:
        print(f"RTSP-Ringpuffer: vorhandene Dateien konnten nicht gelesen werden: {exc}")
        _file_index = 0
        return

    grouped = {}
    for path in candidates:
        idx = _rtsp_slot_index(path)
        if idx is None:
            continue
        try:
            mtime_ns = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
        except Exception as exc:
            print(f"RTSP-Ringpuffer: Dateistatus von {path.name} nicht lesbar: {exc}")
            continue
        grouped.setdefault(idx, []).append((mtime_ns, path))

    # Pro Slot nur die neueste Datei behalten; Altlasten entfernen.
    for idx, items in grouped.items():
        items.sort(key=lambda item: item[0], reverse=True)
        keep_mtime, keep_path = items[0]
        existing[idx] = (keep_mtime, keep_path)

        for _, stale_path in items[1:]:
            try:
                stale_path.unlink()
                print(f"RTSP-Ringpuffer: alte Dublette entfernt: {stale_path.name}")
            except FileNotFoundError:
                pass
            except Exception as exc:
                print(f"RTSP-Ringpuffer: Dublette {stale_path.name} konnte nicht entfernt werden: {exc}")

    for idx in range(MAX_FILES):
        if idx not in existing:
            _file_index = idx
            print(
                f"RTSP-Ringpuffer: {len(existing)}/{MAX_FILES} Plätze belegt; "
                f"starte bei freiem Slot {idx:03d}."
            )
            return

    oldest_idx, (_, oldest_path) = min(
        existing.items(),
        key=lambda item: item[1][0],
    )
    _file_index = oldest_idx
    print(
        f"RTSP-Ringpuffer voll ({MAX_FILES}/{MAX_FILES}); "
        f"ältestes Bild ist {oldest_path.name}. "
        f"Beginne in Slot {oldest_idx:03d} mit dem Überschreiben."
    )


def _frame_filename(idx, frame_wall_time):
    """Stabiler Ringpuffer-Dateiname; echte Frame-Zeit steckt in der mtime."""
    return f"rtsp_{idx:03d}.jpg"



def _write_frame(data, frame_wall_time):
    global _file_index

    idx = _file_index
    name = _frame_filename(idx, frame_wall_time)
    path = _app["IMG"] / name

    # Diagnose vor dem Schreiben
    img_dir = _app["IMG"]
    try:
        exists = img_dir.exists()
        writable = os.access(img_dir, os.W_OK)
    except Exception:
        exists = False
        writable = False

    print(
        f"RTSP-Ringpuffer: Zielordner={img_dir}, "
        f"vorhanden={exists}, schreibbar={writable}, Slot={idx:03d}"
    )

    # Zuerst die neue Datei schreiben. Alte Slot-Dateien werden erst danach
    # entfernt, damit bei einem Schreibfehler kein Bild verloren geht.
    try:
        path.write_bytes(data)
    except Exception as exc:
        print(
            f"RTSP-Ringpuffer FEHLER: Schreiben fehlgeschlagen: "
            f"{path} -> {type(exc).__name__}: {exc}"
        )
        raise

    try:
        size = path.stat().st_size
    except Exception as exc:
        print(
            f"RTSP-Ringpuffer FEHLER: Dateigroesse nicht lesbar: "
            f"{path.name} -> {type(exc).__name__}: {exc}"
        )
        raise

    if size <= 0:
        print(f"RTSP-Ringpuffer FEHLER: Leere Datei geschrieben: {path}")
        try:
            path.unlink()
        except Exception:
            pass
        raise RuntimeError(f"Leere RTSP-Datei geschrieben: {path}")

    # Echte Frame-Zeit auch als mtime setzen.
    try:
        os.utime(path, (float(frame_wall_time), float(frame_wall_time)))
    except Exception as exc:
        print(
            f"RTSP-Ringpuffer WARNUNG: mtime von {name} konnte nicht gesetzt werden: "
            f"{type(exc).__name__}: {exc}"
        )

    # Erst jetzt alte Dateien dieses Ringpuffer-Slots entfernen.
    removed = 0
    for old_path in _slot_files(idx):
        if old_path == path:
            continue
        try:
            old_path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except Exception as exc:
            print(
                f"RTSP-Ringpuffer WARNUNG: alte Slot-Datei "
                f"{old_path.name} konnte nicht entfernt werden: "
                f"{type(exc).__name__}: {exc}"
            )

    print(
        f"RTSP-Ringpuffer GESPEICHERT: {path.name} "
        f"({size} Bytes, alte Slot-Dateien entfernt={removed})"
    )

    _file_index = (_file_index + 1) % MAX_FILES
    return path



def _handle_event(entity, t0):

    print(f"RTSP-Trigger: {entity} -> on")

    _app["pause_door_after_motion"]()



    if not stream_ok():

        print("RTSP: kein aktueller Stream-Frame - Ereignis kann nicht ausgewertet werden.")

        return



    # Nachlaufzeit abwarten, Frames kommen weiter in den Puffer

    time.sleep(max(0.0, t0 + POST - time.monotonic()) + 0.3)



    with _buffer_lock:

        frames = [(t, wall, d) for t, wall, d in _buffer if t0 - PRE <= t <= t0 + POST]



    selected = []

    next_t = -1e18

    for t, wall, d in frames:

        if t >= next_t:

            selected.append((t, wall, d))

            next_t = t + 1.0 / ANALYZE_FPS



    if not selected:

        print("RTSP: keine Frames im Ereignisfenster gefunden.")

        return



    try:
        img_dir = _app["IMG"]
        print(
            f"RTSP-Ereignis: Bildordner={img_dir}, "
            f"vorhanden={img_dir.exists()}, "
            f"schreibbar={os.access(img_dir, os.W_OK)}, "
            f"ausgewaehlte Frames={len(selected)}"
        )
    except Exception as exc:
        print(f"RTSP-Ereignis: Ordnerdiagnose fehlgeschlagen: {type(exc).__name__}: {exc}")

    paths = [_write_frame(d, wall) for _, wall, d in selected]

    print(

        f"RTSP: pruefe {len(paths)} Frames "

        f"({selected[0][0] - t0:+.1f} s bis {selected[-1][0] - t0:+.1f} s um den Trigger): "

        + ", ".join(p.name for p in paths)

    )



    analyze = _app["analyze"]

    person_detected = False

    person_image_name = None

    yellow_found = None



    for p in paths:

        yellow_ok, person_ok, q = analyze(p)

        print(f"{p.name}: Person={person_ok}, Gelb={q:.3f}, Postbote={yellow_ok}")



        if person_ok and person_image_name is None:

            person_detected = True

            person_image_name = p.name



        if yellow_ok:

            yellow_found = (p.name, q)

            break  # Postbote gefunden, restliche Frames nicht noetig



    if person_detected:

        print("PERSON ERKANNT:", person_image_name)

        _app["count_person"]()

        _app["person_hit"](person_image_name)



    if yellow_found:

        print("POSTBOTEN-KANDIDAT:", yellow_found[0])

        _app["count_post"]()

        _app["hit"](*yellow_found)


    # Pro RTSP-Ereignis genau ein Ton; Post hat Vorrang vor Person.
    if yellow_found:
        _app["play_detection_sound"]("post")
    elif person_detected:
        _app["play_detection_sound"]("person")


    if not person_detected and not yellow_found:

        print("RTSP: keine Person im Ereignisfenster erkannt.")





# ---------------------------------------------------------

# Optional: Haustuer-/Garagen-Pruefung aus dem Stream

# ---------------------------------------------------------



def _rtsp_camera_snapshot():

    with _buffer_lock:

        data = _latest_jpeg

        age = time.monotonic() - _last_frame_time



    if data is not None and age < 5.0:

        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)

        if img is not None:

            return data, img



    # Fallback: bisheriger Weg ueber camera_proxy

    return _orig_camera_snapshot()





# ---------------------------------------------------------

# Start

# ---------------------------------------------------------



def start(app_globals):

    """Aus app.py mit globals() aufrufen. Rueckgabe True = RTSP-Modus aktiv."""

    global _orig_camera_snapshot



    _configure(app_globals)



    if ENABLED:
        _initialize_file_index()



    if not ENABLED:

        print("RTSP-Modus deaktiviert - Ordner-Modus aktiv.")

        return False



    if not _app["SUPERVISOR_TOKEN"]:

        raise RuntimeError("SUPERVISOR_TOKEN fehlt. homeassistant_api muss aktiviert sein.")



    print(

        f"RTSP-Modus aktiv: Trigger={', '.join(TRIGGERS)}, "

        f"Fenster -{PRE:g} s / +{POST:g} s, Analyse {ANALYZE_FPS:g} fps, "

        f"Haustuer aus Stream={'ja' if DOOR_USE else 'nein'}"

    )



    if DOOR_USE:

        _orig_camera_snapshot = _app["camera_snapshot"]

        # app.py loest camera_snapshot zur Laufzeit ueber globals() auf

        _app["camera_snapshot"] = _rtsp_camera_snapshot



    threading.Thread(target=_reader, name="rtsp-reader", daemon=True).start()

    threading.Thread(target=_trigger_loop, name="rtsp-trigger", daemon=True).start()

    return True