# Inbetriebnahme: Umstieg vom ESP32-Jarolift-Controller

Ziel: alle Rollläden ohne Neu-Anlernen übernehmen, Schritt für Schritt, mit Rückweg.
Für eine Neuinstallation ohne alten Controller nur die Schritte 3, 4, 6 und 7 ausführen und jeden
Motor anlernen.

## 0. Vorbereitung

- HA-Vollbackup (verschlüsselt).
- Automationen, Skripte und Assist-Befehle, die Rollläden fahren, vorübergehend deaktivieren.
- In der alten WebUI unter *Einstellungen* die `config.json` exportieren.
  **Sie enthält Master-Schlüssel und Passwörter:** nur lokal und verschlüsselt aufbewahren.

## 1. Zählerstand ablesen und alten Controller stilllegen

1. Alte WebUI → *System* → **Gerätezähler** notieren (Wert `C`).
2. Danach **keinen Befehl mehr** über den alten Controller senden.
3. Alten ESP **stromlos** machen. Er darf nie gleichzeitig mit der neuen Brücke senden, sonst
   laufen zwei Zähler mit derselben Seriennummer auseinander.

Startwert für Home Assistant: **`C + 16`**. Der Aufschlag deckt einen eventuell übersehenen Befehl
ab und liegt im KeeLoq-Standardfenster.

Optional, wenn der ESP per USB erreichbar ist: Flash sichern (enthält auch den Zähler im NVS):

```bash
pip install --upgrade esptool
esptool --chip esp32s3 -p /dev/ttyACM0 flash-id
esptool --chip esp32s3 -p /dev/ttyACM0 -b 921600 read-flash 0 0x400000 backup_A.bin
esptool --chip esp32s3 -p /dev/ttyACM0 -b 921600 read-flash 0 0x400000 backup_B.bin
sha256sum backup_*.bin   # müssen gleich sein
```

`--chip` und die Größe (`0x400000` = 4 MB) an den eigenen ESP anpassen.

## 2. Alte MQTT-Entitäten entfernen

1. Einstellungen → Geräte & Dienste → MQTT → Gerät des alten Controllers → **Gerät löschen**.
2. Retained Discovery-Topics löschen, sonst taucht das Gerät wieder auf. Zum Beispiel mit
   MQTT Explorer alle Topics unter `homeassistant/+/<Gerätename>/` leeren, oder:
   `mosquitto_pub -h <broker> -u <user> -P <pass> -r -n -t 'homeassistant/cover/<Gerätename>/<name>/config'`
   (pro Topic).
3. Unter `<mqtt-topic>/cmd/...` dürfen keine retained Befehle liegen.

Wird das übersprungen, vergibt HA neue IDs mit `_2`, und ein Reparaturhinweis erscheint. Nach dem
Aufräumen die Integration neu laden: Die ursprünglichen IDs werden automatisch übernommen.

## 3. Brücke flashen

1. CC1101 an den neuen ESP anschließen: GDO0 → TX-Pin, GDO2 → RX-Pin, SPI (SCK, MISO, MOSI, CS),
   3,3 V, GND.
2. ESPHome Device Builder → neues Gerät → Inhalt von
   [`esphome/example-esp32s3.yaml`](../esphome/example-esp32s3.yaml) einfügen; `board` und Pins
   anpassen.
3. Installieren (beim ersten Mal per USB), Gerät in HA übernehmen.

## 4. Integration einrichten (Senden aus)

1. HACS → Benutzerdefiniertes Repository `https://github.com/SEWADE/jarolift-rf`
   (Typ *Integration*) → herunterladen → HA neu starten.
2. *Jarolift RF* hinzufügen → **Von ESP32-Jarolift-Controller übernehmen**:
   - Brücke wählen
   - `config.json` einfügen
   - Startwert Zähler: **`C + 16`**
   - Senden aktiv: **aus**
3. In der Übersicht Kanäle, Gruppen und Fernbedienungen prüfen. Gruppen mit Maske 0 bekommen
   vorgeschlagene Kanäle; bei Bedarf später unter der Gruppe anpassen.

## 5. Empfangstest (es wird nichts gesendet)

1. Eine Original-Fernbedienung mehrmals drücken (Hoch, Runter, Stopp).
2. Erwartung: Die `event`-Entität der Fernbedienung zeigt die Taste, Attribut `verified: true`.
   Unbekannte Fernbedienungen erscheinen in *Fernbedienung hinzufügen*.

Ergebnis „verified“ heißt: Schlüssel, Bitreihenfolge, Timing und Pegel stimmen.
**Abbruch**, wenn nach mehreren Versuchen nichts ankommt oder `verified` falsch bleibt:
Verdrahtung (GDO2), Antenne, Abstand prüfen; sonst Rückweg (Abschnitt 8).

## 6. Test mit genau einem Rollladen

1. Optionen der Integration → **Senden aktiv** einschalten.
2. Einen gut sichtbaren Rollladen wählen, die anderen Automationen bleiben aus.
3. Nacheinander: **Stopp**, **Runter**, **Stopp**, **Hoch**. Nach jedem Befehl hinsehen.
4. Der Diagnosesensor *Nächster Zählerwert* steigt pro Befehl um 1.
5. Einen Tag normal mit diesem Rollladen arbeiten.

**Abbruchkriterien:**
- Motor reagiert auf drei Befehle hintereinander nicht.
- Ein falscher Motor fährt.
- Fahrt ohne Auslöser.
- Brücke startet neu (Uptime prüfen).

Bei Abbruch: Senden ausschalten, Log und Diagnose sichern, Rückweg (Abschnitt 8).

## 7. Ausrollen

1. Raum für Raum alle Rollläden einmal hoch/runter/stopp testen.
2. Gruppen testen (ein Telegramm für alle Mitglieder).
3. Schattenposition testen.
4. Automationen, Skripte und Assist wieder aktivieren; Timer bei Bedarf mit dem
   Blueprint [`timer.yaml`](../blueprints/automation/jarolift_rf/timer.yaml) anlegen.
5. Zwei Wochen beobachten: Brücken-Uptime, WLAN-Signal, HA-Log.

## 8. Rückweg zum alten Controller

1. In HA: Optionen → **Senden aus**. Den Diagnosesensor *Nächster Zählerwert* notieren (`N`).
2. Neue Brücke stromlos machen bzw. CC1101 zurückstecken.
3. Alten ESP **ohne Netzwerk** starten (Router-Zugang sperren oder MQTT-Automationen aus).
4. In der alten WebUI den Gerätezähler auf **`N + 16`** setzen, **bevor** ein Befehl gesendet wird.
5. Danach normal weiterbetreiben. Die Seriennummer ist dieselbe, kein Neu-Anlernen nötig.

Der Zähler darf nie zurückgestellt werden: Ein Motor ignoriert Befehle, bis der Zähler den zuletzt
akzeptierten Wert übersteigt.
