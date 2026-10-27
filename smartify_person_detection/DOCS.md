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
