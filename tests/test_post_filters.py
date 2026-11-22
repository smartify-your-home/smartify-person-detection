"""Regressionstest: optionale Post-Filter (Zustellzeit, Fahrzeug) ab 1.7.0.

Praxisfall 22.11.2026 (Sonntag, 11:12): Person mit gelber Jacke wurde als
Post gemeldet. Mit aktivem Zustellzeit-Filter muss sie als Person gemeldet
werden; echte Post (Werktag im Zeitfenster bzw. nach Fahrzeug) bleibt Post.

Aufruf:  python3 tests/test_post_filters.py
Laedt nur die Filterfunktionen aus app.py (per AST), ohne Kamera/MQTT/YOLO/HA.
"""
import ast
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

APP = Path(__file__).resolve().parents[1] / "smartify_person_detection" / "app.py"
NEEDED = {
    "_valid_hhmm", "_minutes_since_midnight", "_parse_post_days", "_time_in_window",
    "_ha_entity_state", "_post_schedule_check", "_post_vehicle_check",
    "post_allowed", "apply_post_filters",
}
tree = ast.parse(APP.read_text(encoding="utf-8"))
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in NEEDED]
nodes += [n for n in tree.body if isinstance(n, ast.Assign)
          and any(getattr(t, "id", "") == "_WEEKDAY_ALIASES" for t in n.targets)]
assert {n.name for n in nodes if isinstance(n, ast.FunctionDef)} == NEEDED, "Filterfunktionen fehlen in app.py"

TZ = timezone(timedelta(hours=1))
STATES = {}


def fake_api(path, payload=None, timeout=10):
    entity = path.rsplit("/", 1)[-1]
    if entity not in STATES:
        raise RuntimeError("404")
    return STATES[entity]


def make(**opts):
    ns = {"datetime": datetime, "timezone": timezone, "quote": quote, "print": lambda *a, **k: None,
          "_ha_api_request": fake_api}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP), "exec"), ns)
    ns.update({
        "POST_SCHEDULE_ENABLED": opts.get("schedule", False),
        "POST_DAYS": ns["_parse_post_days"](opts.get("days", "mo,di,mi,do,fr,sa")),
        "POST_TIME_START": opts.get("start", "07:00"),
        "POST_TIME_END": opts.get("end", "17:00"),
        "POST_WORKDAY_ENTITY": opts.get("workday", ""),
        "POST_REQUIRE_VEHICLE": opts.get("vehicle", False),
        "POST_VEHICLE_ENTITIES": opts.get("vehicles", []),
        "POST_VEHICLE_WINDOW_SECONDS": opts.get("window", 180),
    })
    return ns


def check(label, cond):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        check.failed += 1


check.failed = 0

SUN = datetime(2026, 11, 22, 11, 12, tzinfo=TZ)   # Praxisfall
MON = datetime(2026, 11, 23, 9, 30, tzinfo=TZ)
MON_LATE = datetime(2026, 11, 23, 19, 0, tzinfo=TZ)
CAR = "binary_sensor.front_door_fahrzeug"
WD = "binary_sensor.workday_sensor"

# Ohne Filter: unveraendertes Verhalten.
ns = make()
check("ohne Filter: Sonntag erlaubt", ns["post_allowed"](SUN)[0])

ns = make(schedule=True)
check("Zeitfilter: Sonntag gesperrt", not ns["post_allowed"](SUN)[0])
check("Zeitfilter: Montag 09:30 erlaubt", ns["post_allowed"](MON)[0])
check("Zeitfilter: Montag 19:00 gesperrt", not ns["post_allowed"](MON_LATE)[0])
check("leere Tage -> alle Tage", make(schedule=True, days=" ")["post_allowed"](SUN)[0])
check("englische Tage", not make(schedule=True, days="mon,tue")["post_allowed"](datetime(2026, 11, 25, 9, 0, tzinfo=TZ))[0])

STATES.clear(); STATES[WD] = {"state": "off"}
check("Arbeitstag-Sensor off sperrt", not make(schedule=True, workday=WD)["post_allowed"](MON)[0])
STATES[WD] = {"state": "on"}
check("Arbeitstag-Sensor on erlaubt", make(schedule=True, workday=WD)["post_allowed"](MON)[0])
STATES.clear()
check("Arbeitstag-Sensor Fehler -> fail-open", make(schedule=True, workday=WD)["post_allowed"](MON)[0])

ns = make(vehicle=True, vehicles=[CAR])
STATES[CAR] = {"state": "on", "last_changed": (MON - timedelta(seconds=5)).isoformat()}
check("Fahrzeug aktuell on -> erlaubt", ns["post_allowed"](MON)[0])
STATES[CAR] = {"state": "off", "last_changed": (MON - timedelta(seconds=60)).astimezone(timezone.utc).isoformat()}
check("Fahrzeug vor 60 s off -> erlaubt", ns["post_allowed"](MON)[0])
STATES[CAR] = {"state": "off", "last_changed": (MON - timedelta(seconds=900)).isoformat()}
check("Fahrzeug vor 15 min -> gesperrt", not ns["post_allowed"](MON)[0])
STATES[CAR] = {"state": "unavailable", "last_changed": MON.isoformat()}
check("Fahrzeug unavailable -> gesperrt", not ns["post_allowed"](MON)[0])
STATES.clear()
check("Fahrzeug nicht abfragbar -> fail-open", ns["post_allowed"](MON)[0])
check("ohne Fahrzeug-Entity -> fail-open", make(vehicle=True)["post_allowed"](MON)[0])

# Herabstufung: Post -> Person, Bildname bleibt erhalten.
ns = make(schedule=True)
ns["datetime"] = types.SimpleNamespace(now=lambda: SUN, fromisoformat=datetime.fromisoformat, strptime=datetime.strptime)
y, p, name = ns["apply_post_filters"](("rtsp_1.jpg", 0.4), False, None)
check("gesperrt: kein Post, aber Person mit Treffer-Bild", y is None and p is True and name == "rtsp_1.jpg")
y, p, name = ns["apply_post_filters"](None, True, "a.jpg")
check("ohne Gelb-Treffer unveraendert", y is None and p is True and name == "a.jpg")
ns["datetime"] = types.SimpleNamespace(now=lambda: MON, fromisoformat=datetime.fromisoformat, strptime=datetime.strptime)
y, p, name = ns["apply_post_filters"](("rtsp_2.jpg", 0.4), True, "rtsp_1.jpg")
check("erlaubt: Post bleibt Post", y == ("rtsp_2.jpg", 0.4) and name == "rtsp_1.jpg")

print("FEHLGESCHLAGEN: %d" % check.failed if check.failed else "Alle Tests bestanden.")
sys.exit(1 if check.failed else 0)
