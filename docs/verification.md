# Ausgefuehrte Pruefungen und offene Abnahme

**Aktueller Status (15. November 2026):** Die folgenden Windows-/Installerwerte sind historische lokale Nachweise und werden nicht automatisch dem aktuellen `main`-Commit zugerechnet. Der aktuelle reproduzierbare Build pinnt Node **22.23.5** und prüft einen sauberen Arbeitsbaum; ein neuer Windows-2025-Lauf und eine native Windows-11-Abnahme wurden in dieser Sitzung nicht ausgeführt. Nur ein Bericht mit aktuellem Source-Commit, Setup-SHA und allen nativen Kriterien darf als Freigabe gelten.

Stand des historischen Nachweises: 13. November 2026, lokaler Windows-Entwicklungsbuild `0.2.1-dev`.

## Aktuell auf Windows ausgefuehrt

| Pruefung | Ergebnis | Aussagegrenze |
|---|---|---|
| Umgebung | Historischer Windows-11-x64-Build 26200; CPython 3.12.10; Node 22.19.0; Inno Setup 6.7.3; aktueller Bundle-Pin: Node 22.23.5 | Keine Windows-10-Freigabe |
| Python-Suite | 117 Tests: 113 bestanden, 4 uebersprungen | Nicht-Windows-Test und 3 Symlink-Tests auf diesem Host uebersprungen |
| Node-Suite | 9 Tests: 8 bestanden, 1 uebersprungen | Symlink-Test mangels Hostberechtigung uebersprungen |
| Python-/Node-Syntax | Erfolgreich | Keine Aussage ueber echte Konten |
| Abhaengigkeiten | Python-Wheel-Hashes vollstaendig geladen/geprueft; `pip check` und `npm ci --ignore-scripts` erfolgreich | Compiler-/Runnerzustand verhindert Zusage bitidentischer Builds |
| Quell-Runtime | `ready: true` | Protokoll und Komponenten, kein OAuth |
| Quell-GUI | `ready: true`, sechs Ansichten, Dark/Light und 900x640/1180x760 | Temporaeres Profil, keine Kontoanmeldung |
| PyInstaller | Windows-EXE erfolgreich erzeugt | One-Directory; mitgelieferte Unterordner erforderlich |
| Gebuendelte Runtime und GUI | Beide `ready: true`, Exitcode 0 | Manager-EXE, keine drei offiziellen Desktopfenster |
| Echter Installer | Installation, installierte Runtime/GUI, gleichversioniges Upgrade und Deinstallation erfolgreich | Temporaerer Installationsordner; kein Cross-Version-Upgrade |
| Externe Daten | Synthetische Datei ausserhalb des Programmordners blieb nach Upgrade/Deinstallation bytegleich | Keine echten Profildaten fuer Tests benutzt |
| Screenshots | Eigenes temporaeres Testfenster, Dark/Light | Kein Figma-Bild; keine vollstaendige DPI-Abnahme |
| Desktop-Erkennung | `OpenAI.Codex_26.1106.6628.0_x64__2p2nqsd0c76g0/app/ChatGPT.exe` und dessen `resources/codex.exe` gefunden | Dateierkennung allein belegt keine Start-/Auth-Kompatibilitaet |
| Anmeldepfad | Installierte 0.2.1-dev-EXE zeigt **Anmelden** und **Mit OpenAI anmelden**; offizieller Client-Start/Cancellation-Probe meldete `auth.openai.com` und erhielt `CANCELLED` | Keine vollstaendige OAuth-Anmeldung mit einem echten Konto |

Berichte und Pruefsummen befinden sich lokal unter `evidence/` bzw. in `output/build-evidence.zip` und `output/SHA256SUMS.txt`. `build.json` bindet den Installerhash an Basiscommit und Arbeitsbaumstatus; `source-sha256.json` erfasst auch neue nicht ignorierte Quelldateien. Diese lokalen Aenderungen wurden noch nicht als GitHub Release publiziert.

## Beim nativen Build behobene Fehler

- Python 3.14/Tcl 9: Der PyInstaller-Hook fand die eingebetteten Tcl-Verzeichnisse nicht; die erste EXE startete deshalb nicht korrekt. Der gepruefte Build ist auf CPython 3.12.10/Tcl 8.6 festgelegt.
- GUI-Threadgrenze: Die automatische zyklische Speicherbereinigung konnte Tk-Schriftfinalizer waehrend einer Prozessabfrage im Worker ausfuehren. Ein instrumentierter nativer Build zeigte den blockierten Workerstack. Ein neuer Test reproduzierte den falschen Thread vor der Korrektur und bestand danach. Die GUI sammelt zyklische Objekte nun auf ihrem Besitzerthread und stellt die vorherige GC-Einstellung beim Schliessen wieder her.
- Screenshot-Nachweise: Eine Desktop-Bounding-Box konnte bei verdecktem Testfenster fremde Vordergrundinhalte aufnehmen. Der Capturepfad adressiert jetzt ausschliesslich das eigene Testfenster; es gibt keinen Desktop-Fallback. Die korrigierten Bilder wurden visuell geprueft.
- Der Python-Lockfile benoetigt eine ausdrueckliche Ausnahme von der allgemeinen `*.lock`-Ignore-Regel, damit ein frischer Checkout alle Buildabhaengigkeiten enthaelt.

Die vorhandenen Sicherheits-/Regressionstests fuer Profilpfade, Dateisperren, Kontokataloge, Restart/Rollback, Provider-Framing, Secret-Unterdrueckung und Freigabebindung wurden weiter ausgefuehrt. Echte Provider-/Desktop-Aktionen bleiben dort kontrollierte Fixtures.

## Noch offene Produktfreigabe

| Bereich | Offener Nachweis |
|---|---|
| Pool-Uebernahme | Sichere Uebernahme global gespeicherter Credentials in verwaltete Instanzen fehlt als Funktion |
| Bestehende Legacy-Profile | Echte angemeldete Sessions link-only weiterverwenden und erwartete Originaldateiaenderungen pruefen |
| OAuth und Keyring | Echtes Hinzufuegen, Re-Login, falsche Identitaet, Abbruch, Widerruf/Expiry und Windows-Credential-Manager |
| Multi-Instance | Drei reale offizielle Desktopfenster; Wechsel/Stop/Restart betrifft ausschliesslich das Zielprofil |
| Absturz/Rennen | Native Crash-/PID-Reuse-/Prozessbaum-/ACL-Abnahme; erlaubte Symlink-/Junction-Tests |
| GUI | Alle Bedienelemente, Tastatur/Fokus/Kontrast und 100/125/150/200 Prozent DPI |
| Installation | Upgrade zwischen verschiedenen Produktversionen; weitere Windows-Versionen |
| Distribution | Vollstaendige Lizenzabnahme, eigenes Icon, optional legitime Signierung |
| GitHub | Aktuellen Windows-Workflow ausfuehren, privaten Repositorystatus bewahren, vollstaendige native Freigabe vor Release |

Es wurde kein nativer Gesamtfreigabebericht ausgefuellt und keine vollstaendige Produktfreigabe behauptet. Die gesetzten Release-Blocker bleiben bestehen.

## Historischer Ausgangsstand

Der rekonstruierte Ausgangscommit `55cda8426a1f203abcfffe569e87556034b68dce` und die urspruenglichen 37 Archivdateien bleiben erhalten. Die fruehere Linux-Pruefung hatte keine Windows-GUI-/Installer-Abnahme. Die hier aufgefuehrten nativen Ergebnisse stammen aus dem anschliessenden lokalen Windows-Build; siehe auch [Rekonstruktion](reconstruction.md).
