# Jarolift RF für Home Assistant

Steuert Jarolift-Rollladenmotoren (KeeLoq, 433,92 MHz) direkt aus Home Assistant.
Die komplette Jarolift-Logik läuft in HA: KeeLoq, Rolling-Code-Zähler, Kanäle, Gruppen,
Anlernen, Endpunkte, Schatten. Die Hardware ist nur eine **zustandslose Funkbrücke**
(ESP32 + CC1101 mit ESPHome), die fertige Pulsfolgen sendet und Rohsignale empfängt.

> **Status: Vorabversion.** Auf echter Hardware getestet (ESP32-S3 DevKitC-1 + CC1101, Übernahme
> eines ESP32-Jarolift-Controllers v1.9.0 ohne Neu-Anlernen): Hoch/Runter/Stopp aller Kanäle und
> Gruppentelegramme funktionieren. Noch nicht an Hardware geprüft: Schatten, Endpunkte, Anlernen,
> Fernbedienungsempfang.
> Fertig: Protokollkern (bitgenau gegen dewenni/ESP32-Jarolift-Controller v1.9.0 getestet),
> Zähler, Sendewarteschlange, Rollläden, Gruppen, Schatten, Anlernen/Ablernen, Endpunkte,
> Einrichtung neu oder per Import der alten `config.json`, Diagnose, Timer-Blueprint,
> Empfang der Original-Fernbedienungen, ESPHome-Brücke.

## Funktionen

| Funktion | Wo |
|---|---|
| Hoch / Runter / Stopp | `cover`-Entität je Kanal und Gruppe |
| Schattenposition anfahren | Button *Schattenposition* oder Aktion `jarolift_rf.shade` |
| Schattenposition speichern | Aktion `jarolift_rf.set_shade` / Konfig-Button |
| Anlernen / Ablernen | Aktionen `jarolift_rf.learn` / `unlearn` (mit `confirm: true`) / Konfig-Buttons |
| Endpunkte setzen / löschen | Aktionen `jarolift_rf.set_endpoint` / `delete_endpoint` / Konfig-Buttons |
| Zähler vorstellen | Aktion `jarolift_rf.set_counter` (nur vorwärts) |
| Timer (Uhrzeit, Sonnenauf-/untergang ± Versatz, Wochentage, frühestens/spätestens) | Blueprint [`timer.yaml`](blueprints/automation/jarolift_rf/timer.yaml) |
| Funkeinstellungen (Senden an/aus, Leistung, Bündelung, Legacy-Lernmodus) | Optionen der Integration |
| Original-Fernbedienungen | `event`-Entität je Fernbedienung (hoch, runter, stopp, Schatten …), Bus-Event `jarolift_rf_remote`; Zustand der zugeordneten Rollläden wird nachgeführt |

**Fernbedienung hinzufügen:** Taste drücken, dann *Fernbedienung hinzufügen* öffnen und die eben
empfangene aus der Liste wählen. Wird ein Telegramm mit der eigenen Seriennummer empfangen (z. B.
weil der alte Controller noch läuft), erscheint ein Reparaturhinweis.

Die Konfig-Buttons (Anlernen, Endpunkte …) sind auf der Geräteseite jedes Kanals vorhanden, aber
standardmäßig deaktiviert, damit sie weder versehentlich noch per Assist ausgelöst werden.

## Installation

1. **Brücke:** Im ESPHome Device Builder ein neues Gerät anlegen und
   [`esphome/example-esp32s3.yaml`](esphome/example-esp32s3.yaml) einfügen, Pins anpassen,
   flashen und das Gerät in Home Assistant hinzufügen.
2. **Integration:** HACS → Benutzerdefinierte Repositories → `https://github.com/SEWADE/jarolift-rf`,
   Typ *Integration* → herunterladen → Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → *Jarolift RF* hinzufügen und wählen:
   - **Neu einrichten:** Master-Schlüssel eingeben; Seriennummer wird erzeugt (oder eigene
     angeben). Rollläden als Liste eintragen oder später als Kanäle hinzufügen, dann jeden Motor
     anlernen (Button *Anlernen* auf der Geräteseite oder Aktion `jarolift_rf.learn`).
   - **Von ESP32-Jarolift-Controller übernehmen:** dessen `config.json` einfügen (übernimmt
     Schlüssel, Seriennummer, Kanäle, Gruppen) und als Startwert des Zählers den alten
     Zählerstand + 16 angeben. Kein Neu-Anlernen nötig.
   Kanäle und Gruppen lassen sich danach jederzeit in HA hinzufügen, umbenennen und ändern.
4. Senden ist zunächst **aus**. Erst nach erfolgreichem Test in den Optionen einschalten.

Die Entitäts-IDs folgen dem Schema des alten MQTT-Controllers: `cover.jarolift_<name>` für
Kanäle und Gruppen. Solange die alten MQTT-Entitäten existieren, vergibt HA `..._2`. Ein
Reparaturhinweis zeigt das an; nach dem Entfernen des alten MQTT-Geräts und Neuladen der
Integration werden die ursprünglichen IDs automatisch übernommen.

Schritt-für-Schritt-Umstieg mit Abbruchkriterien und Rückweg: [docs/INBETRIEBNAHME.md](docs/INBETRIEBNAHME.md).

## Aufbau

| Teil | Ordner |
|---|---|
| HA-Integration (HACS) | `custom_components/jarolift_rf/` |
| Protokollkern ohne HA-Abhängigkeit | `custom_components/jarolift_rf/core/` |
| ESPHome-Brücke | `esphome/` |
| Referenz-Build des Originalcodes + Testvektoren | `tests/reference/`, `tests/vectors/` |

## Tests

```bash
pip install pytest "pytest-homeassistant-custom-component==0.13.371"   # HA 2026.10.0, Python 3.14
python tests/reference/generate_vectors.py   # optional, braucht g++; Vektoren sind eingecheckt
pytest -q
```

`generate_vectors.py` kompiliert den unveränderten Originalcode auf dem PC. Dabei ersetzen
Platzhalter (Stubs) Funkchip und Arduino-Funktionen und schneiden jeden Pegelwechsel an GDO0 mit.
Ergebnis sind Referenzvektoren für alle Befehle, Kanäle, Gruppen und Servicefunktionen.

## Sicherheit

- Master-Schlüssel und Seriennummern werden ausschließlich in der HA-Oberfläche eingegeben.
  Sie stehen nie in diesem Repository, in Logs oder in Diagnosedaten.
- Alle Schlüssel in Tests sind Dummy-Werte.

## Rechtliches

KeeLoq ist eine Technologie von Microchip. Dieses Projekt enthält keine Herstellerschlüssel und
ist nur für den privaten Gebrauch mit eigenen Geräten gedacht. Funkbetrieb nur im Rahmen der
geltenden SRD-Vorschriften (433,05–434,79 MHz).
Drittquellen und Lizenzen: [NOTICE.md](NOTICE.md).
