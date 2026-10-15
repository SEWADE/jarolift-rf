# Jarolift RF für Home Assistant

Steuert Jarolift-Rollladenmotoren (KeeLoq, 433,92 MHz) direkt aus Home Assistant.
Die komplette Jarolift-Logik läuft in HA: KeeLoq, Rolling-Code-Zähler, Kanäle, Gruppen,
Anlernen, Endpunkte, Schatten. Die Hardware ist nur eine **zustandslose Funkbrücke**
(ESP32 + CC1101 mit ESPHome), die fertige Pulsfolgen sendet und Rohsignale empfängt.

> **Status: Vorabversion, noch nicht an echter Hardware getestet.**
> Fertig: Protokollkern (bitgenau gegen dewenni/ESP32-Jarolift-Controller v1.9.0 getestet),
> Zähler, Sendewarteschlange, Rollläden, Gruppen, Schatten, Einrichtung mit Import der alten
> `config.json`, ESPHome-Brücke. Folgt: Anlern-/Endpunkt-Aktionen, Diagnose, Fernbedienungsempfang.

## Installation

1. **Brücke:** Im ESPHome Device Builder ein neues Gerät anlegen und
   [`esphome/example-esp32s3.yaml`](esphome/example-esp32s3.yaml) einfügen, Pins anpassen,
   flashen und das Gerät in Home Assistant hinzufügen.
2. **Integration:** HACS → Benutzerdefinierte Repositories → `https://github.com/SEWADE/jarolift-rf`,
   Typ *Integration* → herunterladen → Home Assistant neu starten.
3. Einstellungen → Geräte & Dienste → *Jarolift RF* hinzufügen. Die `config.json` des alten
   Controllers einfügen (übernimmt Schlüssel, Seriennummer, Kanäle, Gruppen) und den Startwert
   des Zählers angeben (alter Zählerstand + 16).
4. Senden ist zunächst **aus**. Erst nach erfolgreichem Test in den Optionen einschalten.

Die Entitäts-IDs entsprechen denen des alten MQTT-Controllers (z. B.
`cover.jarolift_kuche_esstisch_klein`, `cover.jarolift_kuche`), sofern die alten MQTT-Entitäten
vorher entfernt wurden.

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
