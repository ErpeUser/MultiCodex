# MultiCodex

[Neue Quellcode-/generated-Ordnerstruktur und Entwickler-Setup](LAYOUT.md)

**0.2.1-dev: lokal gebauter und installierbarer Windows-Entwicklungsbuild. Die vollstaendige Produktfreigabe steht noch aus.**

Am 13. November 2026 wurden EXE, portable ZIP und Setup 0.2.1-dev auf Windows 11 x64 gebaut und mit Runtime-, GUI-, Installations-, gleichversionigen Upgrade- und Deinstallationstests geprueft. Die lokalen Dateien liegen unter `generated/runtime/output/`; Buildnachweise und Pruefsummen sind beigelegt. Anleitung: [Installation und Build](installation.md).

MultiCodex verbindet eine native Python/CustomTkinter-Oberflaeche mit getrennten Codex-Desktop-Profilen, profilbezogenen Anmeldungen und einer lesenden Bestandsanzeige fuer `codex-multi-auth`. Das ist ein unabhaengiges Projekt, kein offizielles OpenAI-Produkt.

Die Historie beginnt unveraendert mit `55cda8426a1f203abcfffe569e87556034b68dce`. Alle 37 Dateien des uebergebenen Quellcode-ZIP stimmten bytegenau mit dem Git-Bundle ueberein. Details: [Rekonstruktion](reconstruction.md).

## Was jetzt implementiert ist

- **Verwaltete Instanzen:** eigene Profilverzeichnisse, eigener Electron-Datenbereich und eigene Authentifizierungsverzeichnisse. Start/Stop/Neustart betreffen nur Prozesse mit passendem Profilpfad. Laufende Prozesse werden beobachtet, nicht nur als gestartet angenommen.
- **Profilbezogene Kontowahl:** mehrere getrennte Anmeldungen innerhalb eines verwalteten Profils. Ein Wechsel schliesst nur diese Instanz, aktiviert deren Authentifizierungsverzeichnis und startet sie neu. Fehler loesen Ruecksetzung oder eine ausdrueckliche Wiederherstellungsanforderung aus.
- **Konto hinzufuegen und Re-Login:** Browser-Anmeldung ueber den offiziellen Codex-App-Server, in einem neuen Anmeldeverzeichnis. Vor dem Umschalten werden Abschluss, gespeicherte Identitaet und erneutes Lesen durch einen frischen Serverprozess geprueft. Abbruch vor dem Umschalten belaesst die alte Zuordnung. Eine bereits begonnene Umschalttransaktion wird sicher abgeschlossen bzw. zurueckgesetzt.
- **Bestehende Profile:** ohne Kopieren, Verschieben oder Entschluesseln von Zugangsdaten verknuepfen. Ihre urspruenglichen Speicherformate bleiben unveraendert. Der Start der offiziellen Anwendung schreibt weiterhin in das verknuepfte Originalprofil; davor wird gewarnt.
- **Bestandsanzeige des Multi-Auth-Pools:** gepinnte Version `2.26.0`, oeffentlicher Speicherpfad, strikt lesende Auswertung des bekannten v3-Formats. Keine Erststart-Migration und keine globale Kontoauswahl. Zugangsdaten werden nicht an Python/GUI ausgegeben.
- **GUI:** sechs Ansichten, deutsche Bedienung, persistentes Dark/Light-Theme, begrenzte Hintergrundjobs, keine Prozessabfrage beim Rendern, Schutz vor Doppelaktionen, Abbruch und Wiederherstellung. Nutzungswerte stammen aus dem offiziellen App-Server; unbekannte Werte bleiben unbekannt.

**Pruefumfang:** Automatisierte Tests mit temporaeren Profilen, echte Windows-Widgets sowie die gebaute und installierte Manager-EXE wurden ausgefuehrt. Echte OAuth-Anmeldungen und drei getrennte offizielle Desktop-Instanzen sind damit noch nicht nachgewiesen.

## Noch nicht erfuellt

| Anforderung | Tatsaechlicher Stand |
|---|---|
| Gespeicherte globale Pool-Konten ohne neues Login einer verwalteten Instanz zuweisen | **Nicht implementiert.** Die sichere Uebernahme der gepoolten Tokens in den verschluesselten offiziellen Authentifizierungsspeicher ist offen. Bestandsanzeige ist keine Uebernahme. |
| Bereits getrennt angemeldete Legacy-Profile weiterverwenden | Verknuepfungs- und Startcode vorhanden; Originaldateien bleiben unveraendert. Reale Windows-Pruefung offen. |
| Neue kombinierte ChatGPT-Desktop-App | Nicht verifiziert. Die Erkennung kennt nur `OpenAI.Codex_*/app/ChatGPT.exe`. |
| Echte GUI-/DPI-Abnahme und Screenshots | Widgets und zwei Themes in zwei Fenstergroessen unter Windows geprueft; nur das eigene Testfenster wird aufgenommen. Vollstaendige Tastatur-/DPI-Abnahme offen. |
| Windows-Installer und GitHub Release | Setup lokal gebaut; Installation, gleichversioniges Upgrade und Deinstallation geprueft. Kein GitHub Release veroeffentlicht. |
| Reproduzierbare Abhaengigkeiten | Python-3.12-x64-Buildlock mit Wheel-Hashes und npm-Lock mit `npm ci` geprueft. Node-Archiv gepinnt; Compilerhash wird erfasst. Vollstaendig bitidentische Builds sind nicht zugesagt. |
| Eigenes Anwendungssymbol, Signierung | Versionsressource vorhanden; eigenes Icon und Signatur fehlen. Keine SmartScreen-Zusage. |

Das Zielrepository ist das oeffentliche [`ErpeUser/MultiCodex`](https://github.com/ErpeUser/MultiCodex). Zugangsdaten, lokale Profile, Laufzeitausgaben und private Nachweise bleiben ausserhalb des versionierten Baums. Veroeffentlichungs- und Release-Aussagen benoetigen weiterhin die native Abnahme aus [Installation](installation.md) und [Pruefmatrix](verification.md).

## Bedienung

1. Unter **Instanzen** ein neues verwaltetes Profil erstellen oder ein bereits getrenntes Codex-Profil verknuepfen.
2. Oben rechts **Anmelden** oder links **Konten** und dann **Anmeldungen** waehlen. In **Gespeicherte Anmeldungen** die Zeile des gewuenschten verwalteten Profils markieren, **Anmeldung hinzufügen** klicken und die Neustart-Rueckfrage fuer dieses Profil bestaetigen. Die Anmeldung erfolgt im offiziellen Browser auf `auth.openai.com`; MultiCodex hat kein Passwortfeld.
3. Weitere Anmeldungen hinzufuegen; mit **Konto wechseln** die Zuordnung genau dieses Profils wechseln. Die vorherige Anmeldung bleibt auswaehlbar.
4. **Erneut anmelden** erwartet dieselbe bekannte Identitaet. Unter **Diagnose** koennen unterbrochene Umschaltungen ausdruecklich wiederhergestellt werden.

Wenn die offizielle Anwendung einen angeforderten normalen Fensterabschluss nicht beendet, wird nicht ungefragt zwangsbeendet. Ein separater, bestaetigungspflichtiger Befehl ist unter Diagnose vorhanden.

## Entwicklungsstart auf Windows

Der lokale Setup-Build installiert die Anwendung unter `%LOCALAPPDATA%\Programs\MultiCodex`. Python und Node werden fuer die installierte Version mitgeliefert. Fuer die Entwicklung:

```powershell
py -3.12 -m venv generated/runtime/dependencies/python/venv
generated\runtime\dependencies\python\venv\Scripts\python.exe -m pip install --require-hashes -r generated/project/config/python/requirements-build.windows-x64.lock
.\tools\setup_node_deps.ps1
generated\runtime\dependencies\python\venv\Scripts\python.exe run.py --self-check --report generated/runtime/evidence/runtime-check.json
generated\runtime\dependencies\python\venv\Scripts\python.exe run.py
```

Das Windows-Buildskript ist auf CPython 3.12.10 x64 und Node 22.23.5 festgelegt. Die [historischen Windows-Pruefberichte](verification.md) nennen Node 22.19.0; die native Pruefung mit der aktualisierten Laufzeit steht noch aus. Python 3.14/Tcl 9 wird vom Paketierer derzeit abgewiesen. Eine passende offizielle Codex-Installation wird weiterhin benoetigt. Neue Anmeldungen verlangen `cli_auth_credentials_store = "keyring"`; siehe [Sicherheit](security.md).

```powershell
generated\runtime\dependencies\python\venv\Scripts\python.exe -m unittest discover -s tests -v
node --test bridge/tests/service.test.mjs
generated\runtime\dependencies\python\venv\Scripts\python.exe -m compileall -q multicodex tools run.py
generated\runtime\dependencies\python\venv\Scripts\python.exe run.py --gui-smoke --report generated/runtime/evidence/gui-check.json
```

`--self-check` prueft Laufzeitabhaengigkeiten und Protokoll, nicht echte Konten. `--gui-smoke` erstellt nur ein temporaeres Testprofil und rendert echte Widgets, keine echten Kontoanmeldungen. Fehlende Komponenten liefern Exitcode 1.

## Build, Design und Nachweise

`./tools/build_windows.ps1` fuehrt den kompletten lokalen Build inklusive Installerpruefung aus. [Build und Release](installation.md) erklaert Voraussetzungen und Freigabe fuer exakt einen Commit und Installer-Hash. [Pruefmatrix](verification.md) trennt ausgefuehrte Tests von fehlender Abnahme.

[Figma-Entwurf](https://www.figma.com/design/iKeNG6k7TfG5U98yfqKFxI), [DESIGN.md](../specifications/DESIGN.md), [UX-CONTRACT.md](../specifications/UX-CONTRACT.md), [Drittanbieterhinweise](../licenses/THIRD_PARTY_NOTICES.md). Die Figma-Frames sind Entwuerfe, keine Screenshots dieser Windows-Anwendung.
