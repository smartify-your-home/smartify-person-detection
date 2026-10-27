# Smartify Person Detection

Lokale Personen- und Post-Erkennung für Home Assistant mit YOLO11/ONNX, RTSP-Ringpuffer,
MQTT Discovery und optionaler Tür-/Garagentor-Kantenerkennung.

## Installation

Diese Software ist eine **Home-Assistant-App (Supervisor Add-on)**. Sie wird daher über den
Home Assistant **App Store** als benutzerdefiniertes App-Repository installiert:

1. **Einstellungen → Apps → App Store**
2. Menü **Repositories**
3. `https://github.com/smartify-your-home/smartify-person-detection` hinzufügen
4. **Smartify Person Detection** installieren

> HACS installiert keine Supervisor-Apps. Die Repository-Struktur ist deshalb für den
> Home-Assistant-App-Store aufgebaut; HACS ist für diesen App-Typ nicht der Installer.

## Erkennungston

Optional kann bei jeder neuen Erkennung ein Home-Assistant-Mediaplayer einen Ton abspielen.
Ein Post-Treffer ist zugleich eine Person; pro Ereignis wird trotzdem nur **ein** Ton
ausgegeben, wobei der **Post-Ton Vorrang** hat.

Beispiel:

- Mediaplayer: `media_player.wohnzimmer`
- Person: `/local/sounds/person.mp3`
- Post: `/local/sounds/post.mp3`

Für `/local/...` versucht die App automatisch `internal_url` bzw. `external_url` von
Home Assistant zu verwenden. Bei Bedarf kann eine eigene HA-Basis-URL gesetzt werden.

## Automatische Resets

Automatische Timer-Resets für Person/Post sowie der Binary-Reset um Mitternacht sind
standardmäßig **deaktiviert**. Die Optionen können einzeln aktiviert werden.

## RTSP-Ringpuffer

Standardmäßig werden bis zu **100** Bilder als stabile Dateien
`rtsp_000.jpg` bis `rtsp_099.jpg` geführt. Die tatsächliche Frame-Zeit wird als Datei-mtime
gespeichert und erscheint damit als `Last-Modified`.

## Version

Aktuell: **1.6.0**
