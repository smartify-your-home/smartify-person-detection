# Smartify Person Detection – Dokumentation

Smartify Person Detection ist eine lokale Home-Assistant-App für Personen- und Post-Erkennung mit YOLO11/ONNX, RTSP-Ringpuffer, MQTT Discovery sowie optionaler Tür-/Garagentor-Kantenerkennung.

## Konfiguration

Die normale Home-Assistant-App-Seite **Konfiguration** ist die zentrale Stelle für MQTT, Erkennung, Reset-Verhalten, Sound, RTSP sowie Tür-/Garagentor-Optionen.

Die Ingress-Weboberfläche **Bildbereiche & Kalibrierung** ist ausschließlich für Kamerabild, Personen-ROI und die Kalibrierung der Tür-/Garagentor-Kanten vorgesehen.

## Sound

Die Sound-Konfiguration erfolgt auf der normalen App-Konfigurationsseite. Dort stehen die Sound-Optionen zusammenhängend:

- `sound_enabled`
- `sound_media_player`
- `person_sound`
- `post_sound`
- `sound_time_window_enabled`
- `sound_time_start`
- `sound_time_end`
- `sound_media_content_type`
- `sound_base_url`

Sounddateien unter `/homeassistant/www/sounds/` sind über `/local/sounds/...` erreichbar.

Die App veröffentlicht drei MQTT-Switches:

- `switch.smartify_person_detection_sound`
- `switch.smartify_person_detection_person_sound`
- `switch.smartify_person_detection_post_sound`

Damit kann Sound global sowie für Person und Post getrennt stummgeschaltet werden.

## Slideshow

Die Slideshow wird nach `/homeassistant/www/slideshow_persondetection.html` installiert und ist unter `/local/slideshow_persondetection.html` erreichbar. Der Bildpfad folgt automatisch dem konfigurierten `image_dir`.

## Changelog

Der vollständige Changelog befindet sich direkt bei der App unter **Changelog** sowie im Repository.


## Sound-URL-Auflösung

Für Sounddateien unter `/local/...` gilt ab 1.6.9:

- `sound_absolute_url: false` (Standard): der relative Pfad `/local/sounds/...` wird unverändert an `media_player.play_media` übergeben. Das entspricht dem Verhalten einer normalen Home-Assistant-Automation und ist besonders für Browser Mod geeignet.
- `sound_absolute_url: true`: die App erzeugt eine absolute URL. Priorität: manuelle `sound_base_url`, danach `external_url`, danach `internal_url`.

Für MP3 ist `sound_media_content_type` standardmäßig `audio/mpeg`.


## Dynamische Sounddatei-Auswahl

Die dynamische Sounddatei-Auswahl befindet sich auf der eigenen App-Seite **Sound testen**. Dort wird die Liste beim Öffnen aus `/homeassistant/www/sounds/` aufgebaut. Eine Auswahl setzt intern automatisch den passenden `/local/sounds/...`-Pfad.

Wenn eine lokal konfigurierte Sounddatei fehlt, wird eine persistente Home-Assistant-Benachrichtigung erzeugt. Ein allein eingetragener Dateiname wird automatisch auf einen eindeutigen Treffer im Soundordner aufgelöst.

Die in 1.6.10/1.6.11 verwendeten MQTT-`select`-Entities für Person/Post werden ab 1.6.12 per leerem retained Discovery-Payload entfernt.


## Sound-Testseite

Die App-Weboberfläche enthält eine eigene Seite **Sound testen**, getrennt von **Bildbereiche & Kalibrierung**. Sie zeigt Mediaplayer, URL-Modus, Basis-URL, Medientyp, Zeitfenster, Sound-Freigaben sowie die effektiven Person-/Post-Dateien.

Die Seite listet die gefundenen Dateien aus `/homeassistant/www/sounds/` und kann eine Datei als Laufzeit-Auswahl für Person bzw. Post übernehmen.

Die beiden Test-Schaltflächen verwenden **denselben Codepfad wie die automatische Wiedergabe** und kein `force=True`:

1. globaler Sound-Schalter muss EIN sein
2. der jeweilige Person-/Post-Schalter muss EIN sein
3. der konfigurierte Zeitbereich muss aktuell erlauben
4. die ausgewählte/konfigurierte Sounddatei muss verfügbar sein
5. dieselbe Pfadauflösung wird verwendet
6. derselbe konfigurierte Mediaplayer wird angesprochen
7. derselbe Aufruf von `media_player.play_media` wird ausgeführt

Die in 1.6.11 angelegten MQTT-Testbutton-Entities werden beim Discovery-Lauf von 1.6.12 wieder entfernt.
