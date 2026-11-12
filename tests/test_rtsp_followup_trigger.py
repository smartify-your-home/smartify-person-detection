"""Regressionstest: Folge-Trigger waehrend der RTSP-Sperrphase.

Spielt den realen Ablauf vom 12.11.2026 08:07 nach (Postauto faehrt vor,
Zusteller steigt erst nach dem Fahrzeug-Trigger aus) und prueft Rearm,
Flatterschutz und "keine Doppelerkennung".

Aufruf:  python3 tests/test_rtsp_followup_trigger.py
Benoetigt weder Kamera, MQTT noch YOLO; cv2/numpy werden bei Bedarf gestubbt.
"""
import sys
import types
from pathlib import Path

for _name in ("cv2", "numpy"):
    try:
        __import__(_name)
    except Exception:  # pragma: no cover - nur ohne installierte Pakete
        sys.modules[_name] = types.ModuleType(_name)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "smartify_person_detection"))
import rtsp_source as rs  # noqa: E402

PERSON = "binary_sensor.front_door_person"
CAR = "binary_sensor.front_door_fahrzeug"


class Stop(Exception):
    pass


class Sim:
    """Simulierte Uhr, Trigger-Zeitleisten, Ringpuffer und app.py-Callbacks."""

    def __init__(self, timeline, visible, t_end, buffer_fps=4.0):
        self.t = 0.0
        self.timeline = timeline          # entity -> [(t_on, t_off), ...]
        self.visible = visible            # {"person": [(a, b)], "post": [(a, b)]}
        self.t_end = t_end
        self.calls = []                   # (zeit, callback, argument)
        self.analyzed = []                # Frame-Zeiten, die ausgewertet wurden
        self.windows = []
        self.frame_time = {}
        self.dt = 1.0 / buffer_fps
        self.next_frame = 0.0

    # --- Uhr -------------------------------------------------------
    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        target = self.t + max(0.0, seconds)
        while self.next_frame <= target:
            rs._buffer.append((self.next_frame, 1_000_000.0 + self.next_frame, b"x"))
            self.next_frame += self.dt
        keep = rs.PRE + rs.POST + 2.0
        while rs._buffer and rs._buffer[0][0] < target - keep:
            rs._buffer.popleft()
        self.t = target
        rs._latest_jpeg = b"x"
        rs._last_frame_time = self.t
        if self.t > self.t_end:
            raise Stop()

    # --- HA-Trigger --------------------------------------------------
    def entity_on(self, entity):
        return any(a <= self.t < b for a, b in self.timeline.get(entity, []))

    # --- Ringpuffer-Datei / Analyse ------------------------------------
    def write_frame(self, data, wall):
        name = f"rtsp_{len(self.frame_time):03d}.jpg"
        self.frame_time[name] = wall - 1_000_000.0
        return types.SimpleNamespace(name=name)

    def _in(self, kind, t):
        return any(a <= t <= b for a, b in self.visible.get(kind, []))

    def analyze(self, p):
        t = self.frame_time[p.name]
        self.analyzed.append(round(t, 3))
        post = self._in("post", t)
        person = post or self._in("person", t)
        return post, person, (0.4 if post else 0.0)

    def cb(self, name):
        def _f(*args):
            self.calls.append((round(self.t, 2), name, args[0] if args else None))
        return _f

    def names(self):
        return [c[1] for c in self.calls]

    def run(self):
        rs._buffer.clear()
        rs.TRIGGERS = [PERSON, CAR]
        rs.PRE, rs.POST, rs.ANALYZE_FPS = 2.0, 3.0, 2.0
        rs.POLL, rs.REARM_OFF, rs.MAX_FILES = 0.5, 10.0, 60
        rs._app = {
            "IMG": Path("/nonexistent"),
            "pause_door_after_motion": lambda: None,
            "analyze": self.analyze,
            "count_person": self.cb("count_person"),
            "person_hit": self.cb("person_hit"),
            "count_post": self.cb("count_post"),
            "hit": self.cb("hit"),
            "play_detection_sound": self.cb("sound"),
            "play_detection_announcement": self.cb("announce"),
        }
        rs._entity_on = self.entity_on
        rs._write_frame = self.write_frame
        rs.time = types.SimpleNamespace(monotonic=self.monotonic, sleep=self.sleep, time=lambda: self.t)
        self.sleep(5.0)  # Puffer vorfuellen
        try:
            rs._trigger_loop()
        except Stop:
            pass
        return self


def check(label, cond):
    print(("OK   " if cond else "FAIL ") + label)
    if not cond:
        check.failed += 1


check.failed = 0

# Zeiten relativ zu 08:07:00, +10 s Vorlauf (Sekunde 25 = 08:07:15).
T = 10.0

# 1) Realer Ablauf 12.11.2026: Fahrzeug 08:07:14.99-21.83 und 28.12-33.21,
#    Person 08:07:18.57-29.06, Zusteller sichtbar ca. 08:07:19.5-23.
s = Sim(
    {CAR: [(T + 14.99, T + 21.83), (T + 28.12, T + 33.21)], PERSON: [(T + 18.57, T + 29.06)]},
    {"post": [(T + 19.5, T + 23.0)]},
    t_end=T + 60,
).run()
check("1 Postauto: genau ein Post-Treffer", s.names().count("hit") == 1 and s.names().count("count_post") == 1)
check("1 Postauto: Post-Ton und Post-Ansage genau einmal",
      [c for c in s.calls if c[1] in ("sound", "announce")] and
      [c[2] for c in s.calls if c[1] == "sound"] == ["post"] and
      [c[2] for c in s.calls if c[1] == "announce"] == ["post"])
check("1 Postauto: Person genau einmal gemeldet", s.names().count("person_hit") == 1)
check("1 Postauto: kein Frame doppelt ausgewertet", len(s.analyzed) == len(set(s.analyzed)))
check("1 Postauto: zweites Fahrzeug-ON (Abfahrt) loest nichts mehr aus", max(c[0] for c in s.calls) < T + 28)

# 2) Altes Verhalten waere: nur Fahrzeug, niemand steigt aus -> kein Treffer, ein Ereignis.
s = Sim({CAR: [(T + 15, T + 22)]}, {}, t_end=T + 60).run()
check("2 Nur Fahrzeug: keine Meldung", s.calls == [])
check("2 Nur Fahrzeug: nur ein Fenster (max. 2 fps * 5 s + 1)", len(s.analyzed) <= 11)

# 3) Flatternder Sensor: derselbe Trigger mehrfach ON in der Sperrphase -> ein Ereignis.
s = Sim({PERSON: [(T + 15, T + 17), (T + 20, T + 22), (T + 25, T + 27)]},
        {"person": [(T + 13, T + 30)]}, t_end=T + 60).run()
check("3 Flattern: Person genau einmal", s.names().count("person_hit") == 1 and s.names().count("count_person") == 1)
check("3 Flattern: ein Ton", s.names().count("sound") == 1)

# 4) Person zuerst, Fahrzeug danach, Person in beiden Fenstern sichtbar -> keine Doppelerkennung.
s = Sim({PERSON: [(T + 15, T + 30)], CAR: [(T + 21, T + 26)]},
        {"person": [(T + 13, T + 30)]}, t_end=T + 70).run()
check("4 Person+Fahrzeug: Person nur einmal gezaehlt", s.names().count("count_person") == 1)
check("4 Person+Fahrzeug: nur ein Ton/eine Ansage", s.names().count("sound") == 1 and s.names().count("announce") == 1)

# 5) Beide Trigger gleichzeitig ON -> ein Ereignis, kein Folge-Ereignis.
s = Sim({PERSON: [(T + 15, T + 20)], CAR: [(T + 15, T + 20)]}, {}, t_end=T + 60).run()
check("5 Gleichzeitig: nur ein Fenster", len(s.analyzed) <= 11)

# 6) Rearm: nach 10 s durchgehend OFF loest derselbe Sensor wieder aus.
s = Sim({PERSON: [(T + 15, T + 17), (T + 45, T + 47)]},
        {"person": [(T + 13, T + 18), (T + 43, T + 48)]}, t_end=T + 80).run()
check("6 Rearm: zwei getrennte Personen-Ereignisse", s.names().count("person_hit") == 2)

# 7) Post schon im ersten Fenster -> kein Folge-Ereignis mehr.
s = Sim({PERSON: [(T + 15, T + 30)], CAR: [(T + 21, T + 26)]},
        {"post": [(T + 13, T + 30)]}, t_end=T + 70).run()
check("7 Post im ersten Fenster: genau ein Post-Treffer", s.names().count("hit") == 1 and s.names().count("sound") == 1)

print("\nERGEBNIS:", "alle Tests bestanden" if not check.failed else f"{check.failed} FEHLGESCHLAGEN")
sys.exit(1 if check.failed else 0)
