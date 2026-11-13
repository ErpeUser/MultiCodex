# Rekonstruktion und Reparatur vom 13. November 2026

## Verfuegbare Belege

Ausgewertet wurden der in dieser Unterhaltung verfuegbare Verlauf, die Anhaenge, das Quellcode-ZIP und das Git-Bundle. Nicht verfuegbare fruehere Arbeitsordner oder ausgelassene Nachrichten wurden nicht als rekonstruiert ausgegeben. Es wurden keine internen Gedankennotizen als Projektbelege verwendet.

- Ausgangscommit: `55cda8426a1f203abcfffe569e87556034b68dce`, Branch `main`.
- `MultiCodex-source-0.1.0-dev.zip`: 37 Projektdateien, alle identisch zu diesem Git-Commit.
- `MultiCodex-commit-history.bundle`: erfolgreich geklont, Historie erhalten.
- Die erneut hochgeladenen Anhaenge `(2)` und `(8)` sind bytegleich: SHA-256 `4f134a1679c16b444a83a704b88433807b63ac7bec009e4e7d537c3e18b85233`.
- Reproduzierte Baseline: 21 Python-Tests und 3 Node-Tests bestanden. Das war kein Beleg fuer fertige Kontozuordnung, Re-Login, Windows-GUI oder Installer.
- Figma-Datei und zwei Entwurfsframes sind im Verlauf durch Toolantworten belegt. Kein fertiger Windows-Screenshot war enthalten.

## Warum nicht alles neu geschrieben wurde

Der gesicherte Stand war vorhanden und intern konsistent. Eine Neuimplementierung haette erhaltene Historie und Tests weggeworfen. Stattdessen wurden vorhandene Module gezielt erweitert bzw. unsichere Pfade ersetzt. Unbelegte fruehere Fertigmeldungen wurden nicht uebernommen.

Die frueheren wiederholten Quelltextabfragen und begonnenen/unterbrochenen Agentenaktionen im sichtbaren Verlauf belegen keine fertige Implementierung. Ausschlaggebend sind die wiederhergestellten Dateien, ausgefuehrte Tests und echte Artefakte.

## Festgestellte Funktionsluecken und Korrekturen

| Ausgangszustand | Reparatur / Nachweis |
|---|---|
| Globale Multi-Auth-Auswahl als naechstliegender Kontowechsel | Globales Umschalten im Adapter gesperrt; GUI verwendet jetzt profilgebundene SessionController-Transaktionen. |
| Re-Login nicht verdrahtet | Offizieller App-Server, separater Anmeldebereich, Identitaets- und Persistenzpruefung, anschliessender Zielneustart. Synthetische Tests, keine reale OAuth-Abnahme. |
| Neues Konto konnte die vorherige Anmeldung aus der Auswahlliste verdraengen | Vorherige Identitaet erhalten; Hinzufuegen und Rueckwechsel werden getestet. |
| Fehlerhafte Metadaten und JSON-Antworten | Strikte Formen, Versionspruefung, Feld-Allowlist, Groessenlimits und feste Fehlermeldungen. |
| Windows-Geraetenamen und doppelte Profilaliasnamen | Zusaetzliche Validierung, Gross-/Kleinschreibung und gesperrte Katalogmutationen. |
| Symlinks/Junctions in Profil- oder Sperrpfaden | Abweisung, keine Weiterleitung von Schreibaktionen auf fremde Ziele. |
| Geerbte globale Authentifizierungsumgebung | Isolierte CODEX_HOME-/Electron-/CLI-Umgebung; globale Rotation deaktiviert. |
| Alte Profilpfad-Kommandozeilen nicht erkannt | Sowohl Profilwurzel als auch Electron-Unterordner erkannt, mehrdeutige Argumente abgewiesen. |
| Unlesbarer Kandidatenprozess wie ein fehlender Prozess behandelt | Unbekannter Status statt falschem Leerlauf; keine erratene Prozessaktion. |
| Ungesicherte gleichzeitige Aktionen | Betriebssystem-Sperren, atomare Metadaten, Backup und Wiederherstellungsjournal. |
| GUI-I/O und unbeschraenkte Worker | Worker-Limit, Ergebnisqueue, gecachter Snapshot, ein Prozessscan pro Aktualisierung, keine Tk-Aufrufe aus Workern. |
| Selbsttest pruefte nur lebenden Transport | Fehlende GUI-/Node-/Upstream-Komponenten verhindern Erfolg. |
| Windows-GUI-EXE ohne zuverlaessiges Warten geprueft | Workflow wartet explizit auf den gestarteten Prozess und prueft Exitcode plus Bericht. |
| Release allein an Tag und Build gekoppelt | Native Abnahme muss zum exakten Commit UND Installer-Hash passen; geschuetzte Release-Umgebung vorgesehen. |

## Entscheidungen und ihre Kosten

1. **Historie erhalten.** Keine komplette Neuentwicklung. Preis: bestehende Plattformgrenzen bleiben sichtbar.
2. **Privates MultiCodex.** Die konkrete Vorgabe am Anfang hat Vorrang vor dem generischen spaeteren Absatz zum oeffentlichen Repository. Bei gegenteiliger Auslegung bliebe das Projekt zu restriktiv, nicht versehentlich oeffentlich.
3. **Vorhandener Stack und Farben.** Kein dritter Designversuch; Verhalten zuerst. Preis: Figma-zu-Windows-Pixeltreue weiterhin nicht nachgewiesen.
4. **Neue Logins ueber offiziellen App-Server und Keyring.** Kein selbstgebautes OAuth und kein Klartext-Tokenexport. Preis: der bereits gespeicherte globale Multi-Auth-Pool ist weiterhin nur lesbar, nicht sicher in neue Instanzen uebernehmbar.
5. **Unbekannte Installation ablehnen.** Kein Raten von ChatGPT-2026-Pfaden. Preis: neue kombinierte Desktop-Builds koennen nicht gestartet werden, bis sie nativ geprueft sind.
6. **Kein Release ohne Nachweis.** Ein lokaler Testlauf ersetzt keinen Installer. Preis: aktuell kein Endbenutzer-Download.

## Grenzen dieser Sitzung

Linux statt Windows; CustomTkinter und das gepinnte Upstream-Modul fehlen. Node ist 22.16.0 statt mindestens 22.19. Paketdownloads scheiterten an der Umgebung. Es gibt weder ein nutzbares Windows-Buildsystem noch eine authentifizierte GitHub-CLI. Der GitHub-Connector meldete fuer `ErpeUser/MultiCodex` HTTP 404; das bedeutet fehlend oder nicht erreichbar, nicht sicher nicht existent.

Das Projekt liegt als gepruefter Entwicklungsstand mit erhaltenem Git-Verlauf vor. Es ist nicht als fertig, fehlerfrei, installierbar oder veroeffentlicht eingestuft.
