# Jarolift RF für Home Assistant

Steuert Jarolift-Rollladenmotoren (KeeLoq, 433,92 MHz) direkt aus Home Assistant.
Die komplette Jarolift-Logik läuft in HA: KeeLoq, Rolling-Code-Zähler, Kanäle, Gruppen,
Anlernen, Endpunkte, Schatten. Die Hardware ist nur eine **zustandslose Funkbrücke**
(ESP32 + CC1101 mit ESPHome), die fertige Pulsfolgen sendet und Rohsignale empfängt.

> **Status: in Entwicklung.** Noch nicht installierbar.
> Fertig: Protokollkern (KeeLoq, Telegramm, Befehlssequenzen), Bit für Bit gegen den
> Originalcode von dewenni/ESP32-Jarolift-Controller v1.9.0 getestet.

## Aufbau

| Teil | Ordner |
|---|---|
| HA-Integration (HACS) | `custom_components/jarolift_rf/` |
| Protokollkern ohne HA-Abhängigkeit | `custom_components/jarolift_rf/core/` |
| ESPHome-Brücke (folgt) | `esphome/` |
| Referenz-Build des Originalcodes + Testvektoren | `tests/reference/`, `tests/vectors/` |

## Tests

```bash
pip install pytest
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
