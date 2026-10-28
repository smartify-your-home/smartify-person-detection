# Changelog

## 1.6.18

- Reset-Topics auf genau drei Varianten bereinigt
- `<prefix>/person_reset` setzt nur Person auf OFF
- `<prefix>/post_reset` setzt nur Post auf OFF
- `<prefix>/reset` setzt Person und Post gemeinsam auf OFF
- vorübergehenden Legacy-Alias `<prefix>/person/reset` wieder entfernt
- MQTT-Subscriptions und Start-Log entsprechend bereinigt

## 1.6.17

- Person-only Reset ergänzt: `<prefix>/person_reset`
- Legacy-Topic `<prefix>/person/reset` wird ebenfalls wieder unterstützt
- Gesamtreset `<prefix>/reset` und Post-Reset `<prefix>/post_reset` bleiben erhalten
- kritischen MQTT-Bug behoben: veralteter Aufruf `publish_sound_select_states()` konnte den MQTT-`on_connect`-Callback mit `NameError` abbrechen
- dadurch konnten MQTT-Nachrichten wie manuelle Resets nach dem Verbindungsaufbau nicht zuverlässig verarbeitet werden
- Reset-Subscriptions und Start-Log erweitert
- Auto-Reset-/Mitternachtsverhalten dokumentiert

## 1.6.16

- zweite, getrennte Weboberfläche **Sound & Zeit** ergänzt
- ROI-/Kalibrieroberfläche bleibt ausschließlich für Bildbereiche und Tür-/Garagentor-Kalibrierung
- dynamische Liste vorhandener `media_player.*`-Entities
- rekursiver Scan aller unterstützten Audiodateien unter `/homeassistant/www/` → `/local/...`
- Sound- und Zeiteinstellungen werden persistent unter `/data/sound_settings.json` gespeichert und sofort aktiv
- URL-Modi: relativ, **Extern-Automatik** über Home-Assistant-`external_url`, manuelle Basis-URL
- Anzeige von Home-Assistant-`external_url` und `internal_url`
- separater URL-Test für Person- und Post-Sound
- separater Sound-Test über exakt denselben `media_player.play_media`-Pfad wie die automatische Erkennung
- Fehler behoben: Laufzeit-Soundauswahl verwendet jetzt tatsächlich die gespeicherten Sound-Einstellungen statt nur der Startwerte aus `config.yaml`

## 1.6.15

- Sound-Testseite wieder vollständig aus der Ingress-Weboberfläche entfernt
- Ingress ist wieder ausschließlich für ROI, Bildbereiche und Tür-/Garagentor-Kalibrierung reserviert
- Sound-Konfiguration bleibt ausschließlich auf der normalen Home-Assistant-App-Seite **Konfiguration**
- Dateiprüfung für lokale Sounddateien bleibt aktiv und erzeugt bei fehlenden Dateien eine persistente HA-Warnmeldung
- Dokumentation klargestellt: native App-Konfiguration unterstützt keine dynamischen Dateidropdowns und keine eigenen Testbuttons

## 1.6.14

- **Sound testen** wird beim Öffnen der App-Weboberfläche jetzt direkt angezeigt
- Person- und Post-Testknöpfe sind dadurch ohne zusätzlichen Zwischenschritt sichtbar
- Audiodatei-Suche auf den gesamten Home-Assistant-`/local/`-Bereich erweitert
- rekursiver Scan von `/homeassistant/www/` statt nur `/homeassistant/www/sounds/`
- unterstützt weiterhin MP3, WAV, OGG, M4A, AAC und FLAC
- vollständiger `/local/...`-Pfad wird automatisch für die ausgewählte Datei verwendet
- **Bildbereiche & Kalibrierung** bleibt als getrennte Seite erreichbar

## 1.6.13

- Startfehler aus 1.6.12 behoben: falsche Einrückung im Sound-Auswahl-Endpunkt verursachte `IndentationError`
- Sound-Testseite und App-Auswahl starten wieder korrekt

## 1.6.12

- MQTT-Testbutton-Entities aus Home Assistant wieder entfernt
- alte retained MQTT-Discovery-Einträge der 1.6.11-Testbuttons werden automatisch gelöscht
- die in 1.6.10/1.6.11 verwendeten MQTT-Select-Entities für Sounddateien werden ebenfalls entfernt; die Auswahl erfolgt jetzt direkt auf der App-Seite
- eigene App-Seite **Sound testen** ergänzt, getrennt von ROI/Bildbereiche & Kalibrierung
- App-Weboberfläche startet jetzt mit Auswahl zwischen **Sound testen** und **Bildbereiche & Kalibrierung**
- Sound-Testseite zeigt die aktuell geladene Konfiguration und alle gefundenen Audiodateien
- Person-/Post-Datei kann auf der Testseite ausgewählt und der effektive Pfad direkt kontrolliert werden
- Test verwendet weiterhin exakt denselben Playback-Codepfad wie die automatische Erkennung, ohne `force=True`

## 1.6.11

- zwei Home-Assistant-Testbuttons für Person- und Post-Ton ergänzt
- Testbuttons verwenden exakt denselben Wiedergabepfad wie eine automatische Erkennung
- Test berücksichtigt globalen Sound-Schalter, getrennten Person/Post-Schalter und zulässigen Zeitbereich
- Test verwendet dieselbe ausgewählte Sounddatei, Pfadauflösung, Mediaplayer-Entity und `media_player.play_media`
- blockierte Tests schreiben einen klaren Grund ins App-Protokoll

## 1.6.10

- dynamische Sounddatei-Auswahl als MQTT-`select` für Person und Post
- alle unterstützten Audio-Dateien unter `/homeassistant/www/sounds/` werden automatisch als `/local/sounds/...` angeboten
- ausgewählter Pfad wird persistent gespeichert und automatisch für die Wiedergabe verwendet
- fehlende lokal konfigurierte Sounddateien erzeugen eine persistente Home-Assistant-Warnmeldung
- nur eingetragener Dateiname wird bei eindeutigem Treffer automatisch auf den vollständigen `/local/sounds/...`-Pfad aufgelöst
- unterstützt MP3, WAV, OGG, M4A, AAC und FLAC

## 1.6.9

- Soundwiedergabe an das Verhalten einer funktionierenden Home-Assistant-Automation angepasst
- `/local/sounds/...` wird standardmäßig unverändert an `media_player.play_media` übergeben
- neue Option `sound_absolute_url`: nur bei Bedarf absolute Sound-URL erzeugen
- Standard-`media_content_type` für MP3 von `music` auf `audio/mpeg` geändert
- absolute URL bleibt optional mit Priorität: `sound_base_url` → `external_url` → `internal_url`
- verbessert insbesondere die Wiedergabe über Browser Mod / Browser-Mediaplayer auf iPad

## 1.6.8

- Sound-URL-Auflösung verbessert: `external_url` wird jetzt vor `internal_url` bevorzugt
- manuell konfigurierte `sound_base_url` behält weiterhin höchste Priorität
- Protokoll zeigt jetzt an, welche Basis-URL für die Soundwiedergabe verwendet wird
- verbessert die Soundwiedergabe auf extern über HTTPS verbundenen Clients wie iPads

## 1.6.7

- Home-Assistant-App-Changelog direkt im Add-on-Ordner ergänzt, damit der Changelog auch auf der App-Seite verfügbar ist
- `DOCS.md` und `README.md` im Add-on-Ordner ergänzt, damit Dokumentation und Hinweise direkt bei der App mitgeliefert werden
- Root-Dokumentation und Add-on-Dokumentation auf denselben Release-Stand gebracht

## 1.6.6

- Sound-Konfiguration aus der ROI-/Kalibrieroberfläche entfernt
- Sound-Optionen auf der nativen Home-Assistant-App-Konfigurationsseite zusammenhängend sortiert
- native App-Konfiguration ist wieder alleinige Quelle für Mediaplayer, Sounddateien und Zeitfenster
- alte in `/data/sound_settings.json` gespeicherte Werte aus 1.6.3–1.6.5 werden nicht mehr bevorzugt
- Ingress-Seite wieder klar als **Bildbereiche & Kalibrierung** bezeichnet
- MQTT-Sound-Schalter bleiben unverändert verfügbar

## 1.6.5

- Sound-Bereich aus den Tür-/Garagenabschnitten herausgenommen und direkt unter **System & Kamera** platziert
- drei Sound-Schalter mit festen Standard-Entity-IDs veröffentlicht
- MQTT-Discovery-Veröffentlichung der Sound-Schalter wird jetzt bestätigt und im Log protokolliert
- Beschriftungen der Sound-Schalter vereinheitlicht: **Sound gesamt**, **Person-Ton**, **Post-Ton**

## 1.6.4

- Ingress-Seite von „Kalibrierung“ auf **Smartify Person Detection – Einstellungen** umbenannt
- Kopfbereich der Weboberfläche klarer strukturiert
- System-/Kamerastatus und Sound-Konfiguration in einer gemeinsamen Einstellungsoberfläche gebündelt

## 1.6.3

- drei persistente Home-Assistant-Sound-Schalter per MQTT Discovery: Gesamt, Person und Post
- Person- und Post-Ton getrennt stummschaltbar
- optionaler erlaubter Sound-Zeitbereich mit Start-/Endzeit
- Zeitfenster über Mitternacht werden unterstützt
- Mediaplayer-Vorschläge direkt aus den vorhandenen `media_player.*`-Entities
- Sounddatei-Vorschläge aus `/local/sounds/` (MP3, WAV, OGG, M4A, AAC, FLAC)
- Person- und Post-Ton direkt aus der Ingress-Weboberfläche testbar
- Sound-Einstellungen können in der Ingress-Weboberfläche gespeichert werden

## 1.6.2

- Slideshow übernimmt den konfigurierten `image_dir` automatisch
- `/homeassistant/www/...` wird automatisch auf den passenden `/local/...`-Pfad abgebildet
- Slideshow übernimmt `rtsp_max_files` automatisch, begrenzt auf maximal 100 Bilder
- verständliche Fehlermeldung, wenn `image_dir` nicht unter `/homeassistant/www` liegt
- `rtsp_max_files` in der App-Konfiguration auf 1 bis 100 begrenzt

## 1.6.1

- integrierte Bildanzeige **Slideshow Persondetection**
- automatische Installation nach `/local/slideshow_persondetection.html`
- neutraler mittelgrauer Hintergrund für helle und dunkle Home-Assistant-Themes
- Slideshow auf Ringpuffer `rtsp_000.jpg` bis `rtsp_099.jpg` angepasst

## 1.6.0

- Rebranding auf **Smartify Person Detection**
- Repository-Struktur für den Home-Assistant-App-Store
- automatische Person-/Post-Resets standardmäßig deaktiviert
- Mitternachts-Reset der Binary-Sensoren standardmäßig deaktiviert
- optionaler Erkennungston über frei wählbaren `media_player`
- getrennte Sounds für Person und Post
- bei Post-Erkennung nur ein Ton pro Event, Post-Ton hat Vorrang
- `/local/sounds/...` wird nach Möglichkeit automatisch auf die Home-Assistant-URL aufgelöst
- RTSP-Ringpuffer weiterhin bis zu 100 JPGs mit stabilen Dateinamen und echter mtime
- Branding von MQTT Discovery, Panel, App-Namen und Standard-Entity-IDs aktualisiert

## 1.5.1

- stabile RTSP-Dateinamen `rtsp_000.jpg` bis `rtsp_099.jpg`
- echte Frame-Zeit in der Datei-mtime / `Last-Modified`

## 1.5.0

- periodischen Selbstneustart entfernt
- unnötige zyklische Garbage Collection entfernt
- RTSP-State-Bereinigung
