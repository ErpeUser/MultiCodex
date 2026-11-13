# Ausgefuehrte Pruefungen und offene Abnahme

Stand: 13. November 2026, Entwicklungsstand 0.2.0-dev.

## Lokal ausgefuehrt

| Pruefung | Ergebnis | Aussagegrenze |
|---|---|---|
| Git-Bundle wiederhergestellt und Source publiziert | Ausgangscommit 55cda8426a1f203abcfffe569e87556034b68dce erhalten; vollständiger Quellbaum auf `main` veröffentlicht | Kein Windows-/Installer-Nachweis |
| ZIP mit wiederhergestelltem Commit verglichen | 37 Dateien, 0 Unterschiede | Belegt nur den erhaltenen Entwicklungsstand |
| Baseline Python / Node | 21 / 3 bestanden | Alte zentrale Funktionsluecken dadurch nicht abgedeckt |
| Aktuelle Python-Suite | 109 Tests bestanden | Linux, temporaere Daten, Provider-/Desktop-Fixtures |
| Aktuelle Node-Suite | 9 Tests bestanden | Echter Node-Unterprozess, Upstream-Fassade bei Inventartests kontrolliertes Testpaket |
| Python-Compilation / Node-Syntax | Erfolgreich | Kein Installer- oder GUI-Nachweis |
| Workflow YAML | Geparst | Nicht auf Windows ausgefuehrt |
| Runtime-Selbsttest | **Nicht bereit, Exitcode 1** | CustomTkinter fehlt, Node 22.16 statt >=22.19, Upstream-Paket fehlt |
| Echter GUI-Smoke-Test | **Konnte nicht starten, Exitcode 1** | Fehlende GUI-Abhaengigkeit; kein Screenshot erzeugt |

Die Python-Umgebung hat psutil 7.2.2; der Windows-Build pinnt 6.1.1. Dieser Unterschied ist keine bestaetigte Windows-Kompatibilitaet. Keine echten Benutzerkonten wurden fuer Tests verwendet.

## Konkrete Regressionen und Integrationsgrenzen

- Profilnamen, Gross-/Kleinschreibung, reservierte Windows-Namen, Traversal, Symlinks/Junctions, doppelte Links und Metadatenformen werden getestet.
- Echte Betriebssystem-Dateisperren werden zwischen Threads und getrennten Python-Prozessen geprueft. Die Windows-msvcrt-Variante wurde hier nicht ausgefuehrt.
- Kontowechsel, Re-Login, falsche Identitaet, Abbruch, fehlgeschlagener Stop, fehlgeschlagener Start, Ruecksetzung, Wiederherstellungsjournal und drei getrennte Profile sind mit echten Dateikatalogen getestet. Der Desktop-Prozess selbst ist dabei eine kontrollierte Fixture.
- JSON-Zeilen, Initialisierung, asynchrone Login-Meldung vor der Antwort, Timeout, Abbruch und geheime Fehlertexte werden gegen einen echten gestarteten Test-Unterprozess geprueft. Dieser ist kein OpenAI-Server.
- Node-Inventartests pruefen zulaessige Metadaten, unterdrueckte Tokens, unveraenderte Quelldateien, unbekannte Speicherversionen und abgewiesene Dateiumleitungen. Die echte installierte Upstream-Distribution konnte lokal nicht getestet werden; Import-Nebeneffekte dieser Distribution sind deshalb nicht abschliessend nachgewiesen.
- Nutzungswerte werden ueber das normalisierte Dienstformat getestet; unbekannte Werte werden nicht in 0% umgedeutet.
- Freigabe-Tests pruefen, dass falscher Commit, veraenderte Installer-Bytes, fehlende Kriterien und bloss wahrheitsartige Zeichenketten die Veroeffentlichung sperren. Die verwendete Fake-EXE ist nur Testinhalt und kein Windows-Installer.

## Manuelle und native Abnahme: NICHT erledigt

| Bereich | Offener Nachweis |
|---|---|
| Kontenuebernahme | Globale gespeicherte Pool-Credentials sicher in neue verwaltete Instanzen uebernehmen: Funktion fehlt noch |
| Bereits angemeldete Legacy-Profile | Echte Sessions ohne erneutes Login weiterverwenden, Originaldaten nach Start unveraendert/erwartet aktualisiert |
| OAuth und Keyring | Echtes Hinzufuegen, Re-Login, Widerruf/Expiry, Abbruch, Windows-Credential-Manager-Verhalten |
| Identitaet | Richtiger Account im realen Desktop; Workspace-Isolation bei gleicher E-Mail |
| Multi-Instance | Drei reale Fenster, nur Zielprozess neu gestartet, fremde Prozesse bleiben unberuehrt |
| Absturz/Rennen | Strom-/Prozessabbruch waehrend Stop/Bind/Start, PID-Reuse, wachsende Prozessbaeume, Windows-Dateisperren und ACLs |
| GUI | Alle Bedienelemente, Tastatur, Fokus, Kontrast, Skalierung 100/125/150/200%, echtes Dark/Light-Rendering |
| Installation | Echte Setup-Datei, Erstinstallation, Versionsupgrade, regulare Deinstallation, Erhalt realer Userdaten |
| Kompatibilitaet | Konkrete Windows-/Desktop-/CLI-Versionen, neue kombinierte ChatGPT-App |
| Distribution | Transitive Lockfiles, eigenes Icon, vollstaendige Lizenzpruefung, optional legitime Signatur |
| GitHub | Privates Repository erreichbar; Source-Push auf `main` bestätigt | Für den letzten Commit liegen keine Statuschecks vor; Windows-CI und Release-Asset fehlen |

## Review

Separater **Self-Review**, keine unabhaengige Zweitpruefung: In dieser Sitzung stand kein funktionierendes Subagent-Review-Werkzeug zur Verfuegung. Unter anderem wurden dabei unlesbare Prozesskandidaten, versteckte Profilnamen, Konfigurations-Bypaesse und Metadatentypen untersucht und relevante Fehler durch rote/gruene Regressionstests abgesichert.

Wichtige offene Befunde sind keine Kleinigkeiten: fehlende sichere Pool-Uebernahme, fehlende native GUI/OAuth-/Installer-Abnahme und fehlende vollstaendige Lockfiles blockieren ein fertiges Release.

Nachrangig zur spaeteren Verbesserung: vereinheitlichte Formatierung/Typannotationen, vollstaendige GUI-Automatisierung und staerkere Byte-Begrenzung bereits waehrend des Python-Bridge-Captures. Der eigene Node-Dienst begrenzt die normalen Antworten; der Python-Adapter kontrolliert die Ausgabegroesse erst nach dem Unterprozess-Capture. Kein Schutzversprechen gegen absichtlich boesartige Abhaengigkeiten oder Prozesse desselben Benutzers.
