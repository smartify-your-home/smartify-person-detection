# Smartify Person Detection – Release Notes

Die folgenden Hinweise beschreiben die Änderungen im Quellcode. Ein Eintrag hier **beweist nicht**, dass ein GitHub-Tag, GitHub-Release oder ein installiertes Supervisor-Image bereits existiert. Diese Zustände sind vor einer Veröffentlichung separat zu prüfen.

## v1.6.22 – Pfadeingaben gegen versehentliche Leerzeichen absichern

**Behoben:** Führende/nachgestellte Leerzeichen in `image_dir` und `snapshot_dir` werden entfernt. Leere und relative Verzeichnisangaben werden mit klarer Fehlermeldung abgewiesen.

**Auswirkung:** Ein Eintrag wie ` snapshot_dir: " /homeassistant/www/smartify_person_detection"` führte bisher zu einem relativen Pfad im Container, obwohl die Ausgabe optisch wie ein HA-Pfad aussah.

**Update:** Supervisor-App über den Home-Assistant-App-Store aktualisieren/bei Bedarf neu aufbauen. Nach dem Start die Mount-Meldung prüfen. Ein zuvor in das Container-Overlay geschriebenes Bild wird nicht automatisch übernommen; der nächste echte Trigger erstellt einen neuen Snapshot.

**Prüfstatus:** Quellcodeänderung vorhanden; vollständige Ende-zu-Ende-Validierung in einer frisch gestarteten HA-App nur durch Laufzeitprotokoll und Sichtprüfung nachweisbar.

## v1.6.21 – Home-Assistant-Mountschutz

**Behoben:** Vor `mkdir -p /homeassistant/www` und der Installation der Slideshow kontrolliert `run.sh`, ob `/homeassistant` tatsächlich gemountet und beschreibbar ist. Fehlender Mount beendet die App mit einer klaren Meldung.

**Wichtig:** `homeassistant_config` gehört unter `/homeassistant`; `/data` sind Add-on-eigene Daten. Das Mapping ist in `config.yaml` mit `read_only: false` konfiguriert. Ein Restart allein repariert keine unpassende installierte Containerkonfiguration garantiert.

## v1.6.20 – Sichere Personen- und Post-Snapshots

**Behoben:** `person_latest.jpg` und `post_latest.jpg` werden erst vollständig in eine temporäre Datei geschrieben und dann atomar ersetzt. Die Anwendung liest die Datei zurück, vergleicht den Inhalt und protokolliert den aktuellen Speicherzeitpunkt. MQTT-Snapshot-Attribute verwenden den konfigurierten Ordner statt fester URLs.

**Kompatibilität:** Die beiden stabilen JPG-Dateinamen bleiben erhalten. RTSP-Ringpuffer und Erkennung bleiben unverändert.

**Historischer Hinweis:** Im bestehenden Changelog wird unter derselben Versionsnummer 1.6.20 auch eine Sprachansage-Funktion beschrieben. Die historische Zuordnung ist nicht abschließend geklärt; vor Veröffentlichung eines Tags ist die Git-Historie zu prüfen.

## v1.6.19 – Snapshot-Diagnose

**Neu:** Quell- und Zieldateien werden im Log mit Größe, Zeitstempel, Prüfsumme und Dateisysteminformationen verglichen. Die Diagnose allein repariert keinen Mount.

## Typische Pfade

| Konfiguration | Zweck | Beispiel |
| --- | --- | --- |
| `image_dir` | RTSP-/Motion-Bilder, rotierender Frame-Puffer | `/homeassistant/www/pictures_person_detection` |
| `snapshot_dir` | Letzte erfolgreich erkannte Person/Post | `/homeassistant/www/smartify_person_detection` |
| `person_sound`, `post_sound` | HA-Medienreferenz, kein Linux-Zielordner | `/local/sounds/besuch.mp3` |
| `sound_base_url` | Optionale HTTPS-Basisadresse | Nur bei manuellem URL-Modus |

**Pfadprinzip:** `/homeassistant/www/<ordner>` im App-Container entspricht `/config/www/<ordner>` in Home Assistant und wird per `/local/<ordner>/` ausgeliefert, **wenn** der Home-Assistant-Mount korrekt besteht.

## Für künftige Versionen

Neue und geänderte Funktionen brauchen gleichzeitig aktualisierte `AGENTS.md`-Regeln (falls erforderlich), Root-/App-Changelog, README/DOCS, diese Release Notes, konsistente Versionsmetadaten und aussagekräftige GitHub-Release-Notizen. Ein GitHub-Release darf erst nach tatsächlicher Veröffentlichung als vorhanden gemeldet werden.
