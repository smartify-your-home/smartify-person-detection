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

Sounddateien unter `/homeassistant/www/` sind über `/local/...` erreichbar.

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

- `sound_absolute_url: false` (Standard): der relative Pfad `/local/...` wird unverändert an `media_player.play_media` übergeben. Das entspricht dem Verhalten einer normalen Home-Assistant-Automation und ist besonders für Browser Mod geeignet.
- `sound_absolute_url: true`: die App erzeugt eine absolute URL. Priorität: manuelle `sound_base_url`, danach `external_url`, danach `internal_url`.

Für MP3 ist `sound_media_content_type` standardmäßig `audio/mpeg`.


## Dynamische Sounddatei-Auswahl

Die dynamische Sounddatei-Auswahl befindet sich auf der eigenen App-Seite **Sound testen**. Dort wird die Liste beim Öffnen aus `/homeassistant/www/` aufgebaut. Eine Auswahl setzt intern automatisch den passenden `/local/...`-Pfad.

Wenn eine lokal konfigurierte Sounddatei fehlt, wird eine persistente Home-Assistant-Benachrichtigung erzeugt. Ein allein eingetragener Dateiname wird automatisch auf einen eindeutigen Treffer im Soundordner aufgelöst.

Die in 1.6.10/1.6.11 verwendeten MQTT-`select`-Entities für Person/Post werden ab 1.6.12 per leerem retained Discovery-Payload entfernt.


## Sound-Konfiguration

Alle Sound-Einstellungen werden ausschließlich über die normale Home-Assistant-App-Seite **Konfiguration** vorgenommen. Die Ingress-Weboberfläche bleibt ausschließlich für ROI, Bildbereiche und Tür-/Garagentor-Kalibrierung reserviert.

Die native Supervisor-/App-Konfigurationsseite unterstützt keine dynamischen Dateilisten aus `/local/` und keine benutzerdefinierten Aktionsbuttons. Daher können dort keine automatisch erzeugten Sound-Dropdowns oder Testknöpfe eingebettet werden.

Die App validiert eingetragene lokale Sounddateien beim Start und erzeugt bei fehlenden Dateien eine persistente Home-Assistant-Warnmeldung. Ein eindeutiger Dateiname kann weiterhin automatisch auf den passenden `/local/...`-Pfad aufgelöst werden.

## Fehlerbehebung 1.6.13

Ein Einrückungsfehler im neuen Sound-Auswahl-Endpunkt aus 1.6.12 wurde behoben. Die App startet damit wieder korrekt; die Sound-Testseite bleibt unverändert verfügbar.


## Änderung 1.6.14

Beim Öffnen der App-Weboberfläche wird die Seite **Sound testen** direkt angezeigt. Sie scannt jetzt den gesamten Home-Assistant-`/local/`-Bereich, also rekursiv `/homeassistant/www/`, nach MP3, WAV, OGG, M4A, AAC und FLAC. Dadurch erscheinen auch Audiodateien außerhalb von `/local/sounds/` automatisch in der Auswahlliste. Die Testknöpfe befinden sich direkt neben der Person- bzw. Post-Auswahl; **Bildbereiche & Kalibrierung** bleibt über einen separaten Link erreichbar.


## Änderung 1.6.15

Die Sound-Testseite wurde aus Ingress entfernt. Die Weboberfläche ist wieder ausschließlich für ROI, Bildbereiche sowie Tür-/Garagentor-Kalibrierung vorgesehen.
