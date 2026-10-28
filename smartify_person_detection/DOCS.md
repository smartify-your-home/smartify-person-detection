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


## Sound & Zeit – zweite Weboberfläche

Die ROI-/Kalibrieroberfläche enthält weiterhin keine Sound-Einstellungen. Über **Sound & Zeit** wird eine zweite, getrennte Seite geöffnet.

Diese Seite lädt vorhandene `media_player.*`-Entities aus Home Assistant und scannt rekursiv `/homeassistant/www/` nach MP3, WAV, OGG, M4A, AAC und FLAC. Die gefundenen Dateien werden als `/local/...` angeboten.

Einstellungen werden sofort in `/data/sound_settings.json` gespeichert und gelten ohne App-Neustart. Sie überschreiben die Sound-Startwerte aus der normalen Add-on-Konfiguration.

URL-Modi:

- **Relativer /local/-Pfad** – entspricht einer klassischen HA-Automation.
- **Extern-Automatik** – verwendet ausschließlich die Home-Assistant-`external_url`.
- **Manuelle Basis-URL** – verwendet eine explizit eingetragene HTTP/HTTPS-Basis-URL.

Für Person und Post stehen jeweils zwei Tests bereit:

1. **URL testen** prüft die tatsächlich aufgelöste URL serverseitig und öffnet eine absolute URL zusätzlich im Browser.
2. **Ton testen** verwendet denselben Codepfad wie die automatische Erkennung inklusive Sound-Freigaben, Zeitfenster, Dateiauflösung und `media_player.play_media`.

Fehlt bei Extern-Automatik die `external_url`, wird dies ausdrücklich als Fehler gemeldet.

## Fehlerbehebung 1.6.13

Ein Einrückungsfehler im neuen Sound-Auswahl-Endpunkt aus 1.6.12 wurde behoben. Die App startet damit wieder korrekt; die Sound-Testseite bleibt unverändert verfügbar.


## Änderung 1.6.14

Beim Öffnen der App-Weboberfläche wird die Seite **Sound testen** direkt angezeigt. Sie scannt jetzt den gesamten Home-Assistant-`/local/`-Bereich, also rekursiv `/homeassistant/www/`, nach MP3, WAV, OGG, M4A, AAC und FLAC. Dadurch erscheinen auch Audiodateien außerhalb von `/local/sounds/` automatisch in der Auswahlliste. Die Testknöpfe befinden sich direkt neben der Person- bzw. Post-Auswahl; **Bildbereiche & Kalibrierung** bleibt über einen separaten Link erreichbar.


## Änderung 1.6.15

Die Sound-Testseite wurde aus Ingress entfernt. Die Weboberfläche ist wieder ausschließlich für ROI, Bildbereiche sowie Tür-/Garagentor-Kalibrierung vorgesehen.


## Änderung 1.6.16

Eine zweite Weboberfläche **Sound & Zeit** wurde ergänzt. Die ROI-/Kalibrierseite bleibt inhaltlich getrennt. Die Soundseite speichert Einstellungen persistent, bietet dynamische Mediaplayer- und Audio-Dateilisten, Extern-Automatik über Home Assistants `external_url`, URL-Tests sowie End-to-End-Soundtests.


## MQTT-Reset-Verhalten

Unterstützte Topics:

- `<prefix>/person_reset` – nur Person
- `<prefix>/post_reset` – nur Post
- `<prefix>/reset` – Person und Post gemeinsam

Payload jeweils: `RESET`.

Auto-Reset:

- `person_auto_reset: true` → Person wird nach `person_sensor_on_seconds` zurückgesetzt.
- `post_auto_reset: true` → Post wird nach `binary_sensor_on_seconds` zurückgesetzt.
- Ist der jeweilige Auto-Reset deaktiviert, bleibt der Sensor auf ON, bis ein manueller Reset oder ein Mitternachtsreset erfolgt.
- `reset_binaries_at_midnight: true` setzt Person und Post beim ersten Hauptschleifendurchlauf nach dem lokalen Datumswechsel auf OFF; gleichzeitig werden die Tageszähler zurückgesetzt.


## Änderung 1.6.18

Die Reset-Topics wurden auf genau drei Varianten bereinigt: `person_reset`, `post_reset` und `reset`. Der vorübergehende Legacy-Alias `person/reset` wurde wieder entfernt.
