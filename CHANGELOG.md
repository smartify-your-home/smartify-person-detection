# Changelog

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
