# Changelog

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
