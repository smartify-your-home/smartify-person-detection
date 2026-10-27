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

## Wechsel von älteren „Postbote Detector“-Installationen

Der App-Slug wurde auf `smartify_person_detection` umbenannt. Home Assistant behandelt die App
deshalb als **neue App** und übernimmt den alten `/data`-Bereich nicht automatisch. Vor dem
Entfernen einer älteren Installation sollten insbesondere Tür-/Garagentor-Kalibrierungen und
weitere gewünschte Einstellungen gesichert bzw. in der neuen App neu gesetzt werden.

## Slideshow Persondetection

Beim Start der App wird die mitgelieferte Bildanzeige automatisch nach

`/homeassistant/www/slideshow_persondetection.html`

kopiert und ist in Home Assistant über

`/local/slideshow_persondetection.html`

erreichbar.

Die Slideshow übernimmt den unter `image_dir` konfigurierten Bildordner automatisch. Liegt
`image_dir` z. B. auf `/homeassistant/www/cam_pt2_motion`, verwendet die Slideshow automatisch
`/local/cam_pt2_motion/`. Auch die Anzahl der Ringpufferbilder wird aus `rtsp_max_files`
übernommen (maximal 100). Die Bilder werden nach `Last-Modified` sortiert und die Slideshow
verwendet einen neutralen mittelgrauen Hintergrund.

## Erkennungston

Optional kann bei jeder neuen Erkennung ein Home-Assistant-Mediaplayer einen Ton abspielen.
Ein Post-Treffer ist zugleich eine Person; pro Ereignis wird trotzdem nur **ein** Ton
ausgegeben, wobei der **Post-Ton Vorrang** hat.

In der Ingress-Weboberfläche gibt es dafür eine eigene Sound-Konfiguration:

- Vorschlagsliste mit allen vorhandenen `media_player.*`-Entities aus Home Assistant
- Vorschlagsliste für Audiodateien aus `/homeassistant/www/sounds/`, also `/local/sounds/`
- unterstützte Dateivorschläge: MP3, WAV, OGG, M4A, AAC und FLAC
- getrennte Test-Tasten für Person- und Post-Ton
- optionaler erlaubter Zeitbereich, z. B. `07:00` bis `22:00`
- Zeitfenster über Mitternacht, z. B. `22:00` bis `07:00`, werden unterstützt

Beispiel:

- Mediaplayer: `media_player.wohnzimmer`
- Person: `/local/sounds/person.mp3`
- Post: `/local/sounds/post.mp3`

Für `/local/...` versucht die App automatisch `internal_url` bzw. `external_url` von
Home Assistant zu verwenden. Bei Bedarf kann eine eigene HA-Basis-URL gesetzt werden.

### Sound-Schalter in Home Assistant

Über MQTT Discovery werden drei Schalter angelegt:

- `switch.smartify_person_detection_erkennungston` bzw. die von Home Assistant erzeugte Entity für **Erkennungston**
- **Ton Person**
- **Ton Post**

Damit kann der gesamte Sound oder Person/Post getrennt stummgeschaltet werden. Die Zustände
werden in der App persistent gespeichert und bleiben nach einem Neustart erhalten. Die Schalter
können direkt in Dashboards, Szenen oder Automationen verwendet werden. Der konfigurierte
`sound_enabled`-Wert dient nur als Startwert für den globalen Schalter bei der ersten Einrichtung.

## Automatische Resets

Automatische Timer-Resets für Person/Post sowie der Binary-Reset um Mitternacht sind
standardmäßig **deaktiviert**. Die Optionen können einzeln aktiviert werden.

## RTSP-Ringpuffer

Standardmäßig werden bis zu **100** Bilder als stabile Dateien
`rtsp_000.jpg` bis `rtsp_099.jpg` geführt. Die tatsächliche Frame-Zeit wird als Datei-mtime
gespeichert und erscheint damit als `Last-Modified`.

## Version

Aktuell: **1.6.3**
