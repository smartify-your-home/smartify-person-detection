# AGENTS.md – Smartify Person Detection

**Verbindliche Entwicklungs-, Sicherheits-, Dokumentations- und Release-Regeln.**
Diese Datei bei **jeder** Änderung zuerst vollständig lesen. Sie gilt für alle Menschen und Coding-Agenten; ein schneller Hotfix ist keine Ausnahme.

## 1. Lesepflicht und parallele Entwicklung

1. Vor jedem Edit den aktuellen Remote-Stand von `main`, offene Pull Requests, die neuesten Tags und den letzten **tatsächlich veröffentlichten GitHub-Release** prüfen. Ein Commit oder Versions-Bump ist noch kein veröffentlichtes Release.
2. Erst `AGENTS.md`, `README.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, `smartify_person_detection/config.yaml`, `Dockerfile`, `run.sh`, `DOCS.md` sowie den lokalen App-Changelog lesen. Dann die betroffenen Funktionen in `app.py` und `rtsp_source.py` einschließlich aufrufender Stellen und vorhandener Tests/Workflows untersuchen.
3. Vorherige Fixes in Historie und Changelog prüfen, insbesondere Mounts, RTSP, Snapshot, Audio, MQTT und Kalibrierung. Vor Änderung Zweck, zu erhaltendes Verhalten, Regressionstest und mögliche Migration benennen.
4. Am Repository wird parallel gearbeitet: keine fremden Änderungen überschreiben. Vor jedem API-Write den aktuellen Blob-SHA prüfen; bei Konflikten neu laden und zusammenführen. Keine Force-Pushes, keine umgeschriebenen Tags.

## 2. Architektur und Home-Assistant-Vorgaben

- **Supervisor-App/Add-on, keine HACS-Integration.** Installation über Home Assistant **Apps → App Store**. App-Slug `smartify_person_detection`, Ingress-Port 8099 und MQTT-Entity-IDs nur mit bewusster Migration ändern.
- `smartify_person_detection/config.yaml` muss das HA-Konfigurationsverzeichnis schreibbar einbinden:
  ```yaml
  map:
    - type: homeassistant_config
      read_only: false
  ```
- `/homeassistant` ist der HA-Config-Mount im Container, `/homeassistant/www` entspricht HAs `/local`. `/data` ist der **persistente Add-on-eigene** Speicher. **`/config` im Add-on nicht mit HAs Config verwechseln.**
- Bevor `mkdir`, Slideshow-Kopien, Ringpuffer oder Snapshots geschrieben werden, muss `run.sh` den Mount anhand des **laufenden Containers** überprüfen. Ist `/homeassistant` nicht gemountet: klar abbrechen statt unbemerkt in das flüchtige Container-Overlay zu schreiben. Kein Ersatz-`mkdir -p /homeassistant`.
- Weder gleiche Device-ID mit `/data` fordern noch ein erfolgreiches `copy` als Beweis für Sichtbarkeit im HA-Host behaupten. Mountinfo, Device/Inode und – wenn möglich – dieselbe Zieldatei auf HA-Seite prüfen.

## 3. Vollständiges Pfad-Inventar – bei jedem Eingriff beachten

| Wert | Typ und Quelle | Verwendung und Regel |
| --- | --- | --- |
| `image_dir` | Pfad in nativer App-Konfiguration | RTSP-Ringpuffer und Motion-Eingang; absoluter Pfad, Leerzeichen außen entfernen, nicht in den Container-Layer schreiben; für Slideshow nur unter `/homeassistant/www` über `/local` erreichbar. |
| `snapshot_dir` | Pfad in nativer App-Konfiguration | `person_latest.jpg` / `post_latest.jpg`; absolut, äußere Leerzeichen entfernen; atomar schreiben und zurücklesen; `/local`-Link dynamisch aus diesem Ordner ableiten. |
| `person_sound`, `post_sound` | Sound-Dateiauswahl/Media-Content-ID, **nicht** Linux-Ausgabepfad | Führende/nachgestellte Leerzeichen entfernen; `/local/...` unverändert als relative HA-URL oder über konfigurierten URL-Modus absolut übergeben. Keine Dateinamen irrtümlich als Container-Pfade interpretieren. |
| `sound_base_url`, `sound_absolute_url` | URL/URL-Modus, kein lokaler Dateipfad | Nur gültige Basis-URL im manuellen Modus; URL-Modus und `external_url` erhalten; keine RTSP- oder MQTT-Geheimnisse loggen. |
| `rtsp_url`, `rtsp_username`, `rtsp_password` | RTSP-Quelladresse/Zugangsdaten | Eingaben trimmen, Transport prüfen, Zugangsdaten in Protokollen maskieren. **Kein** Speicherordner. |
| `/homeassistant/www/slideshow_persondetection.html` und `..._config.json` | Feste Ausgabe aus `run.sh` | Nur nach erfolgreicher Mount-Prüfung schreiben; Slideshow-`image_dir` normalisieren und auf `/local` abbilden. |
| `/homeassistant/www` | Fester Sound-Dateisuchpfad | Lesender rekursiver Scan unterstützter Audiodateien; über `/local` referenzieren. |
| `/data/options.json`, `state.json`, `sound_settings.json`, `sound_switches.json`, `sound_selection.json` | Add-on-persistente Konfigurations-/Statusdaten | Im Add-on-`/data` belassen, nicht in das HA-`www` verschieben. |
| `/data/door_* `, `vertical* `, `person_roi.json`, `entity_identity.json` | Kalibrierungs-/Identitätsdaten | Ohne ausdrückliche Migration weder löschen noch umbenennen. Vor Neuinstallation separat sichern. |
| `/app/yolo11n.onnx` | Feste Modell-Datei im Image | Unverändert, nicht als Nutzerdatenordner behandeln. |

**Pfadregeln:** Nutzereingaben `strip()`, danach leeren/relativen Pfad verwerfen; vor Zugriff prüfen, dass Quelle/Ziel existieren oder im tatsächlich gemounteten Bereich sicher angelegt werden können. Verzeichnisse erst nach Mount-Prüfung erzeugen. Für `/local`-URLs nur echte Pfade unter `/homeassistant/www` zulassen. `/data` ist ein anderer Namespace. Änderungen an einem Konfigurationspfad in allen Verbrauchern berücksichtigen (`app.py`, `run.sh`, Slideshow, MQTT, Doku). Fehler nie mit einer irreführenden Erfolgsmeldung verdecken.

## 4. Funktionsschutz

- YOLO11/ONNX, Person-ROI, Gelbanteils-Post-Erkennung und Priorität **Post vor Person** erhalten.
- RTSP-Pre/Post-Trigger, max. 100 Ringpufferbilder mit stabilen Dateinamen und Frame-mtime, Erkennung über ausgewählte Bilder, Fallback **ohne Doppelerkennung** beibehalten.
- Snapshot-Zieldateien atomar ersetzen, nach dem Schreiben gegen die Quelldaten verifizieren, Speicherzeit protokollieren; bei Fehler `SNAPSHOT-FEHLER` statt Erfolg melden.
- MQTT Discovery, Reset-Topics `<prefix>/person_reset`, `<prefix>/post_reset` und `<prefix>/reset`, Zähler sowie manuell/automatisch zurücksetzbare Schalter erhalten.
- Ingress-Oberfläche für ROI/Kalibrierung und separate Seite **Sound & Zeit** bewahren; Sound-Schalter, Zeitfenster, Mediaplayer-Wiedergabe und persistierte Einstellungen schützen.
- Geheimnisse nie in Git, Debug-Ausgaben oder Release-Notes übernehmen.

## 5. Dokumentation und Versionskonsistenz – verpflichtend

Bei **jeder nutzerrelevanten Änderung**, auch bei Hotfixes:
1. `CHANGELOG.md` (Root) um einen **chronologisch korrekt sortierten** Eintrag ergänzen: Version, Datum (soweit bestätigt), Neu/Geändert/Behoben, Migration, bekannte Einschränkungen. Historische Einträge nicht heimlich überschreiben.
2. `smartify_person_detection/CHANGELOG.md` **inhaltlich identisch** halten – dieser ist für die Anzeige im HA-App-Store wichtig.
3. `README.md`, `smartify_person_detection/README.md` und `smartify_person_detection/DOCS.md` aktualisieren, wenn Funktionen, Installation, Pfade oder Konfigurationsoptionen betroffen sind. Keine widersprüchlichen Versionsangaben.
4. `RELEASE_NOTES.md` fortführen: benutzerorientierte Neuerungen, Bugfixes, Upgrade-Schritte, Kompatibilitäts-/Persistenzhinweise, bekannte Probleme, Teststatus. Release-Notes sind **zusätzlich** zum Changelog verpflichtend.
5. Versionen synchronisieren: `smartify_person_detection/config.yaml:version`, Dockerfile-`io.hass.version`, README-Version, Changelog und Release Notes. Für jede ausgelieferte Codeänderung neue Version – keine stillen Änderungen einer bereits veröffentlichten Version.

## 6. Test- und Freigabe-Gates

Vor Push/Tag/Release: Python-Dateien kompilieren, YAML/JSON prüfen, Config-Schema und Docker-Build-Kontext prüfen, wenn möglich fokussierte Regressionstests ausführen. Fehlende Tests explizit als nicht durchgeführt markieren. Mindestens folgende Fälle abdecken:

- Pfade mit führenden/nachgestellten Leerzeichen, relative/leere Pfade, falscher Mount, nicht beschreibbares Ziel, bereits bestehendes `www`.
- Snapshot-Kopie: Person/Post, beschädigtes JPEG, Schreibfehler, identische Prüfsumme, aktueller mtime und dynamische MQTT-URL.
- RTSP-Puffer-Rotation, Trigger-Rearm, Fallback, keine doppelten Ereignisse.
- MQTT-Verbindung/Reset, Post-Priorität, Soundpfad und Sound-Zeitfenster.
- HA-Neustart, Add-on-Neustart und Rebuild, Persistenz von Kalibrierung und Soundoptionen.
- Aktualisierte Benutzer-Doku und **identische** Root-/App-Changelogs.

Tests dürfen nicht gelöscht oder durch pauschales Ignorieren von Fehlern grün gemacht werden. Ohne realen HA-Test ausdrücklich kein funktionierendes Mount oder End-to-End-Verhalten behaupten.

## 7. Veröffentlichungsprozess – wie bei anderen Smartify-Apps

1. Release vorbereiten, Version nach SemVer erhöhen, Doku/Changelog/Release-Notes vor dem Tag vollständig aktualisieren.
2. Add-on-`config.yaml` ist für die Anzeige der Update-Version im Supervisor entscheidend. Die Dockerfile-Version allein genügt nicht.
3. GitHub-Tag `vX.Y.Z` und **GitHub-Release** `vX.Y.Z` mit aussagekräftigen Notes erzeugen; kein Release allein durch Commit/README-Text vortäuschen.
4. GitHub-Release-Inhalt mit `RELEASE_NOTES.md` abgleichen, Tags/Releases nicht überschreiben. Bestehende Workflows respektieren; fehlende Release-Automatik nicht als vorhanden darstellen.
5. Nach Publikation Release/Tag und CI tatsächlich prüfen. Dem Nutzer klar nennen: Commit, Version, **Release veröffentlicht ja/nein**, Installation via App Store und nötigen Rebuild/Neustart.
6. Bei Änderungen am Mount oder App-Slug: vor Deinstallation auf Sicherung der `/data`-Kalibrierungen und Optionen hinweisen.

## 8. Definition of Done / Pflichtbericht

Eine Änderung gilt erst als fertig, wenn Code, Tests/Testeinschränkungen, Root- und App-Changelog, README/DOCS, Release-Notes und Versionsmetadaten konsistent sind. Zum Abschluss kurz berichten: was geändert wurde, welche Prüfungen bestanden, was mangels HA-Laufzeit nicht geprüft wurde und **ob ein echter GitHub-Release existiert**.

## 9. Historische Regressionen (November 2026)

- 1.6.19: Snapshot- und Mount-Diagnose.
- 1.6.20: verifiziertes atomisches Speichern und konfigurationsabhängige MQTT-Snapshot-URLs; historische Changelog-Einträge dürfen nicht mit dem früheren Sprachansage-Eintrag verwechselt werden.
- 1.6.21: Mountschutz vor `mkdir -p`; der Schutz gehört in den Containerstart, nicht bloß in die Snapshotfunktion.
- 1.6.22: Whitespace an `image_dir`/`snapshot_dir` entfernen und relative/leere Eingaben abweisen.
- Diese Punkte und bestehende Sound-/Reset-Fixes sind regressionsempfindlich und müssen vor jedem weiteren Release überprüft werden.

## 10. Übergabe v1.6.23 (2026-11-11)

- 1.6.23 synchronisiert Versionsmetadaten, Root-/App-Changelog, Root-/App-README, `DOCS.md` und `RELEASE_NOTES.md`; diese Dokumentationsänderung ist **kein** zusätzlicher Fix an der Personen-/Post-Erkennung.
- Zuletzt bestätigt: beide App-Verzeichnisse auf `device=2056`, beschreibbar. Nicht als Beleg für einen tatsächlich ersetzten JPG-Snapshot nach dem nächsten Trigger ausgeben.
- Bei späteren Versionen die Benutzer-Release-Notes **vor** dem Versions-Bump fortführen und separat prüfen, ob GitHub-Tag/Release existieren. Der Supervisor-Updatepfad basiert auf `config.yaml:version`, nicht nur auf dem Docker-Label.
