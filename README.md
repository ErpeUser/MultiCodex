# MultiCodex

**0.2.0-dev: wiederhergestellter und reparierter Entwicklungsstand. Kein fertiges Windows-Release.**

MultiCodex verbindet eine native Python/CustomTkinter-Oberflaeche mit getrennten Codex-Desktop-Profilen, profilbezogenen Anmeldungen und einer lesenden Bestandsanzeige fuer `codex-multi-auth`. Das ist ein unabhaengiges Projekt, kein offizielles OpenAI-Produkt.

Die Historie beginnt unveraendert mit `55cda8426a1f203abcfffe569e87556034b68dce`. Alle 37 Dateien des uebergebenen Quellcode-ZIP stimmten bytegenau mit dem Git-Bundle ueberein. Details: [Rekonstruktion](docs/reconstruction.md).

## Was jetzt implementiert ist

- **Verwaltete Instanzen:** eigene Profilverzeichnisse, eigener Electron-Datenbereich und eigene Authentifizierungsverzeichnisse. Start/Stop/Neustart betreffen nur Prozesse mit passendem Profilpfad. Laufende Prozesse werden beobachtet, nicht nur als gestartet angenommen.
- **Profilbezogene Kontowahl:** mehrere getrennte Anmeldungen innerhalb eines verwalteten Profils. Ein Wechsel schliesst nur diese Instanz, aktiviert deren Authentifizierungsverzeichnis und startet sie neu. Fehler loesen Ruecksetzung oder eine ausdrueckliche Wiederherstellungsanforderung aus.
- **Konto hinzufuegen und Re-Login:** Browser-Anmeldung ueber den offiziellen Codex-App-Server, in einem neuen Anmeldeverzeichnis. Vor dem Umschalten werden Abschluss, gespeicherte Identitaet und erneutes Lesen durch einen frischen Serverprozess geprueft. Abbruch vor dem Umschalten belaesst die alte Zuordnung. Eine bereits begonnene Umschalttransaktion wird sicher abgeschlossen bzw. zurueckgesetzt.
- **Bestehende Profile:** ohne Kopieren, Verschieben oder Entschluesseln von Zugangsdaten verknuepfen. Ihre urspruenglichen Speicherformate bleiben unveraendert. Der Start der offiziellen Anwendung schreibt weiterhin in das verknuepfte Originalprofil; davor wird gewarnt.
- **Bestandsanzeige des Multi-Auth-Pools:** gepinnte Version `2.26.0`, oeffentlicher Speicherpfad, strikt lesende Auswertung des bekannten v3-Formats. Keine Erststart-Migration und keine globale Kontoauswahl. Zugangsdaten werden nicht an Python/GUI ausgegeben.
- **GUI:** sechs Ansichten, deutsche Bedienung, persistentes Dark/Light-Theme, begrenzte Hintergrundjobs, keine Prozessabfrage beim Rendern, Schutz vor Doppelaktionen, Abbruch und Wiederherstellung. Nutzungswerte stammen aus dem offiziellen App-Server; unbekannte Werte bleiben unbekannt.

**Pruefumfang:** Diese Implementierung ist durch lokale Tests mit temporaeren Profilen, echten Test-Unterprozessen und simulierten Provider-/Desktop-Grenzen abgesichert. Die echte Windows-Anwendung und echte OAuth-Anmeldungen sind damit noch nicht nachgewiesen.

## Noch nicht erfuellt

| Anforderung | Tatsaechlicher Stand |
|---|---|
| Gespeicherte globale Pool-Konten ohne neues Login einer verwalteten Instanz zuweisen | **Nicht implementiert.** Die sichere Uebernahme der gepoolten Tokens in den verschluesselten offiziellen Authentifizierungsspeicher ist offen. Bestandsanzeige ist keine Uebernahme. |
| Bereits getrennt angemeldete Legacy-Profile weiterverwenden | Verknuepfungs- und Startcode vorhanden; Originaldateien bleiben unveraendert. Reale Windows-Pruefung offen. |
| Neue kombinierte ChatGPT-Desktop-App | Nicht verifiziert. Die Erkennung kennt nur `OpenAI.Codex_*/app/ChatGPT.exe`. |
| Echte GUI-/DPI-Abnahme und Screenshots | Lokal nicht ausgefuehrt: CustomTkinter fehlt und Paketdownloads sind blockiert. Ein echter Widget-Smoketest ist implementiert, aber kein Ersatz fuer die ausstehende Abnahme. |
| Windows-Installer und GitHub Release | Nicht gebaut/veroeffentlicht. Ein Workflow ist vorbereitet, kein Build-Erfolg behauptet. |
| Vollstaendig reproduzierbare Abhaengigkeiten | Direkte Versionen gepinnt; vollstaendige, gepruefte transitive Lockfiles und Runner-/Compiler-Pins fehlen. |
| Eigenes Anwendungssymbol, Signierung | Versionsressource vorhanden; eigenes Icon und Signatur fehlen. Keine SmartScreen-Zusage. |

Zielrepository ist **privat: `ErpeUser/MultiCodex`**. Der verbundene Zugriff lieferte HTTP 404: fehlend oder nicht erreichbar. Die verfuegbare Schnittstelle konnte kein Repository anlegen. Kein Push und kein Download-Link werden vorgetaeuscht.

## Bedienung

1. Unter **Instanzen** ein neues verwaltetes Profil erstellen oder ein bereits getrenntes Codex-Profil verknuepfen.
2. Unter **Konten** fuer das verwaltete Profil **Konto hinzufuegen** waehlen und im offiziellen Browser anmelden. Kein Passwortfeld in MultiCodex.
3. Weitere Anmeldungen hinzufuegen; mit **Konto wechseln** die Zuordnung genau dieses Profils wechseln. Die vorherige Anmeldung bleibt auswaehlbar.
4. **Erneut anmelden** erwartet dieselbe bekannte Identitaet. Unter **Diagnose** koennen unterbrochene Umschaltungen ausdruecklich wiederhergestellt werden.

Wenn die offizielle Anwendung einen angeforderten normalen Fensterabschluss nicht beendet, wird nicht ungefragt zwangsbeendet. Ein separater, bestaetigungspflichtiger Befehl ist unter Diagnose vorhanden.

## Entwicklungsstart auf Windows

Noch keine Endbenutzer-Installationsanleitung: Es liegt keine gepruefte Setup-Datei vor.

```powershell
python -m pip install -r requirements.txt
npm install --prefix bridge --omit=dev --ignore-scripts --no-audit --no-fund
python run.py --self-check --report runtime-check.json
python run.py
```

Python 3.12+, Node 22.19+ und eine passende offizielle Codex-Installation werden benoetigt. Neue Anmeldungen verlangen `cli_auth_credentials_store = "keyring"`; eine automatische Klartext-Rueckfalloption ist nicht vorgesehen. Siehe [Sicherheit](docs/security.md).

```powershell
python -m unittest discover -s tests -v
node --test bridge/tests/service.test.mjs
python -m compileall -q multicodex tools run.py
python run.py --gui-smoke --report gui-check.json
```

`--self-check` prueft Laufzeitabhaengigkeiten und Protokoll, nicht echte Konten. `--gui-smoke` erstellt nur ein temporaeres Testprofil und rendert echte Widgets, keine echten Kontoanmeldungen. Fehlende Komponenten liefern Exitcode 1.

## Build, Design und Nachweise

[Build und Release](docs/installation.md) erklaert die Windows-Pipeline und die notwendige native Freigabe fuer exakt einen Commit und Installer-Hash. [Pruefmatrix](docs/verification.md) trennt ausgefuehrte Tests von fehlender Abnahme.

[Figma-Entwurf](https://www.figma.com/design/iKeNG6k7TfG5U98yfqKFxI), [DESIGN.md](DESIGN.md), [UX-CONTRACT.md](UX-CONTRACT.md), [Drittanbieterhinweise](THIRD_PARTY_NOTICES.md). Die Figma-Frames sind Entwuerfe, keine Screenshots dieser Windows-Anwendung.
