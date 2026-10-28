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

Die Sound-Konfiguration befindet sich auf der normalen **Konfiguration**-Seite der Home-Assistant-App,
also dort, wo auch RTSP, MQTT, Tür- und weitere App-Optionen eingestellt werden.

Die Sound-Optionen stehen dort zusammenhängend in dieser Reihenfolge:

- `sound_enabled` – Startzustand des globalen Sound-Schalters
- `sound_media_player` – gewünschte `media_player.*`-Entity
- `person_sound` – z. B. `/local/sounds/person.mp3`
- `post_sound` – z. B. `/local/sounds/post.mp3`
- `sound_time_window_enabled` – Zeitfenster aktivieren
- `sound_time_start` / `sound_time_end`
- `sound_media_content_type` – für MP3 standardmäßig `audio/mpeg`
- `sound_absolute_url` – standardmäßig **aus**; `/local/...` wird dann unverändert an Home Assistant übergeben
- `sound_base_url` – nur für absolute Sound-URLs optional

Für Browser-Mod-/Browser-Mediaplayer wird standardmäßig genau wie in einer Home-Assistant-Automation der relative Pfad `/local/...` verwendet. Nur wenn `sound_absolute_url` aktiviert ist, wird daraus eine absolute URL.

Ein Post-Treffer ist zugleich eine Person; pro Ereignis wird trotzdem nur **ein** Ton ausgegeben,
wobei der **Post-Ton Vorrang** hat. Zeitfenster über Mitternacht, z. B. `22:00` bis `07:00`,
werden unterstützt.

Die native Supervisor-App-Konfiguration kann keine dynamischen Vorschlagslisten aus den aktuell
vorhandenen Home-Assistant-Entities oder aus dem Dateisystem erzeugen. Deshalb werden Mediaplayer
und Sounddateien dort als Textfelder eingetragen. Die Beschreibungen enthalten passende Beispiele.

### Sounddatei-Auswahl direkt in der App

Die dynamische Dateiliste befindet sich auf der App-Seite **Sound testen** und nicht als zusätzliche Home-Assistant-Entity. Dort werden alle unterstützten Audiodateien unter `/homeassistant/www/` vorgeschlagen und bei der Auswahl automatisch als vollständiger `/local/...`-Pfad verwendet. Unterstützt werden MP3, WAV, OGG, M4A, AAC und FLAC.

Ist eine in der App-Konfiguration eingetragene lokale Sounddatei nicht vorhanden, erzeugt die App zusätzlich eine **persistente Home-Assistant-Warnmeldung** und schreibt den Fehler ins App-Protokoll. Wird nur ein Dateiname eingetragen und dieser ist im Soundordner eindeutig vorhanden, wird der korrekte `/local/...`-Pfad automatisch aufgelöst.

Die kurzzeitig in 1.6.10/1.6.11 angelegten MQTT-`select`-Entities für die Dateiauswahl werden ab 1.6.12 automatisch aus MQTT Discovery entfernt.

### Sound & Zeit – zweite Weboberfläche

Die ROI-/Kalibrieroberfläche bleibt ausschließlich für Bildbereiche sowie Tür-/Garagentor-Kalibrierung reserviert. Zusätzlich gibt es eine **zweite, getrennte Weboberfläche „Sound & Zeit“**.

Dort können ohne App-Neustart eingestellt und gespeichert werden:

- Mediaplayer
- Person- und Post-Sound aus allen gefundenen Dateien unter `/local/`
- Sound gesamt sowie Person/Post getrennt
- erlaubtes Zeitfenster
- Medientyp
- URL-Modus: relativer `/local/`-Pfad, **Extern-Automatik** oder manuelle Basis-URL

Die **Extern-Automatik** verwendet gezielt die in Home Assistant konfigurierte `external_url`. Die Seite zeigt `external_url` und `internal_url` an und bietet für Person/Post jeweils einen **URL-Test** und einen **Sound-Test**.

Der Sound-Test nutzt denselben `media_player.play_media`-Ablauf wie die automatische Erkennung; Sound-Schalter und Zeitfenster werden nicht umgangen. Die Einstellungen werden unter `/data/sound_settings.json` persistent gespeichert und überschreiben die Sound-Startwerte aus der normalen Add-on-Konfiguration.

### Sound-Schalter in Home Assistant

Über MQTT Discovery werden drei Schalter mit festen Standard-Entity-IDs angelegt:

- `switch.smartify_person_detection_sound` – Sound gesamt
- `switch.smartify_person_detection_person_sound` – Person-Ton
- `switch.smartify_person_detection_post_sound` – Post-Ton

Damit kann der gesamte Sound oder Person/Post getrennt stummgeschaltet werden. Die Schalterzustände
werden persistent gespeichert und können direkt in Dashboards, Szenen oder Automationen verwendet werden.

## Automatische Resets

Automatische Timer-Resets für Person/Post sowie der Binary-Reset um Mitternacht sind
standardmäßig **deaktiviert**. Die Optionen können einzeln aktiviert werden.

## RTSP-Ringpuffer

Standardmäßig werden bis zu **100** Bilder als stabile Dateien
`rtsp_000.jpg` bis `rtsp_099.jpg` geführt. Die tatsächliche Frame-Zeit wird als Datei-mtime
gespeichert und erscheint damit als `Last-Modified`.

## Weboberfläche

Die normale Ingress-Hauptseite bleibt ausschließlich für Kamerabild, Personen-ROI, Haustür sowie optionale Garagentor-Kantenmessungen und deren Kalibrierung vorgesehen. Über den separaten Navigationsknopf **Sound & Zeit** wird eine zweite, getrennte Seite geöffnet. RTSP, MQTT und sonstige Basisoptionen bleiben auf der normalen Home-Assistant-Seite **Konfiguration**.

## Version

Aktuell: **1.6.18**


### Manuelle MQTT-Resets

Die App unterstützt drei Reset-Arten:

- `smartify_person_detection/person_reset` – nur Person auf OFF
- `smartify_person_detection/post_reset` – nur Post auf OFF
- `smartify_person_detection/reset` – Person und Post gemeinsam auf OFF

Wenn `person_auto_reset` bzw. `post_auto_reset` deaktiviert sind, bleiben erkannte Sensoren auf ON, bis ein manueller Reset erfolgt oder – falls `reset_binaries_at_midnight` aktiv ist – beim ersten Hauptschleifendurchlauf nach dem Datumswechsel auf OFF gesetzt wird.
