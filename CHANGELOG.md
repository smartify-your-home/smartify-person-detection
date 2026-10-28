# Changelog

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
