# Installation, Windows-Build und Release

## Lokaler Entwicklungsbuild

Am 13. November 2026 wurde Version `0.2.1-dev` auf Windows 11 x64 gebaut. Die gebuendelte und die installierte EXE bestanden Runtime- und GUI-Pruefungen; der Installer bestand Installation, gleichversioniges Upgrade, Deinstallation und Erhalt einer externen synthetischen Testdatei. Das ist eine lokale Entwicklungsdistribution, keine vollstaendige OAuth-/Multi-Instance-Produktfreigabe.

Die Dateien werden lokal unter `output/` erzeugt:

- `Codex-Multi-Studio-Setup-v0.2.1-dev.exe`: normaler Installer.
- `MultiCodex-0.2.1-dev-win-x64-portable.zip`: kompletten Ordner entpacken und `MultiCodex.exe` starten. Die EXE braucht die mitgelieferten Unterordner.
- `build-evidence.zip`: Tests, Runtime-/GUI-Berichte, Installationsnachweis, Quellenmanifest und Buildumgebung.
- `SHA256SUMS.txt`: Pruefsummen dieser Dateien.

Die installierte Anwendung benoetigt keine separate Python- oder Node-Installation. Die offizielle Codex-/ChatGPT-Desktop-Anwendung bleibt eine externe Voraussetzung und wird nicht mitgeliefert. Der lokale Entwicklungsbuild ist nicht signiert. Es wurde kein GitHub Release angelegt.

## Installieren und starten

1. Die Setup-EXE aus `output/` starten.
2. Zielordner ist standardmaessig `%LOCALAPPDATA%\Programs\MultiCodex`; Administratorrechte sind nicht erforderlich.
3. MultiCodex ueber das Startmenue oder die optionale Desktopverknuepfung starten.
4. Oben rechts **Anmelden** oder links **Konten** und dann **Anmeldungen** waehlen. Ist noch kein verwaltetes Profil vorhanden, ueber **Neue Instanz** ein Profil mit einem selbst gewaehlten Namen erstellen.
5. In **Gespeicherte Anmeldungen** die Zeile dieses Profils markieren, **Anmeldung hinzufügen** klicken und die Neustart-Rueckfrage fuer dieses Profil bestaetigen. Der offizielle Browser oeffnet `auth.openai.com`; bei einem Browserfehler kann **Browser erneut öffnen** verwendet oder die Aktion abgebrochen werden.

Programm und Daten liegen getrennt: Profile unter `%LOCALAPPDATA%\MultiCodex\profiles`, Einstellungen unter `%LOCALAPPDATA%\MultiCodex\settings.json`. Verknuepfte Originalprofile bleiben an ihrem Ort. Neue verwaltete Logins verlangen Keyring-Speicherung; siehe [Sicherheit](security.md).

## Entwicklung und Build

Reproduzierbarer Build: CPython **3.12.10 x64**, gebuendeltes Node **22.23.5**, PyInstaller **6.20.0**, und verifizierter Inno Setup **6.7.1 oder 6.7.3**. Der Quellbetrieb akzeptiert weiterhin Node ab **22.19.0**; die portable Windows-Runtime bleibt auf 22.23.5 festgelegt. Die Windows-2025-Workflowumgebung ist ein Server-Buildhost und ersetzt keine native Windows-11-DPI-/OAuth-Abnahme. Python 3.14/Tcl 9 ist fuer diese Paketierung gesperrt, weil der GUI-Ressourcen-Hook die eingebetteten Tcl-Daten nicht korrekt sammelt.

Voraussetzungen bei Bedarf ueber die offiziellen Paketquellen installieren:

```powershell
winget install --id Python.Python.3.12 --exact --version 3.12.10
winget install --id JRSoftware.InnoSetup --exact --version 6.7.3  # 6.7.1 ist auf windows-2025 ebenfalls zulässig
./tools/build_windows.ps1
```

Git ist fuer das Quellenmanifest erforderlich. Das Skript erstellt `.venv`, installiert den vollstaendigen Python-Buildlock mit `--require-hashes`, laedt das offizielle Node-Windows-Archiv mit festem SHA-256 und fuehrt `npm ci --ignore-scripts` aus. Fremde Installationsskripte und eine Multi-Auth-Erststartmigration werden nicht ausgefuehrt.

Danach folgen alle Python-/Node-Tests, Syntaxpruefungen, Quell-Runtime-/GUI-Proben, PyInstaller, Buendelung der Runtime und Lizenzen, beide Proben mit der gebauten EXE, Inno Setup und der tatsaechliche Installationszyklus. GUI-Screenshots erfassen nur das eigene temporaere Testfenster. Fehler stoppen den Ablauf; vorhandene Benutzerkonten werden fuer die Pruefungen nicht verwendet.

Der Installer-Smoke-Test verlangt ein Windows-Konto ohne bereits installierte MultiCodex-Version, damit er keine echte Installationsregistrierung oder Startmenueverknuepfung ersetzt. Nach dauerhafter Installation muss ein erneuter kompletter Buildtest in einem sauberen Testkonto oder einer VM stattfinden. Eine gleichversionige Neuinstallation ist geprueft; ein Upgrade zwischen unterschiedlichen Produktversionen noch nicht.

Der Compiler wird aus den bekannten Inno-Setup-6-Installationsorten genommen oder mit `-InnoCompiler 'C:\Pfad\ISCC.exe'` angegeben. Sein Hash wird festgehalten. CI verwendet denselben Buildbefehl, CPython 3.12.10 und die Windows-2025-Runnerfamilie; der aktuelle Workflow wurde in dieser Sitzung nicht bei GitHub ausgefuehrt. Die Lockfiles sichern die Dependency-Aufloesung, nicht bitidentische Compiler-/Runner-Ergebnisse.

## Buildnachweise

`evidence/build.json` enthaelt Zeit, Betriebssystem, Python-/Node-Version, Node-Archivhash, Compilerhash, Setuphash und Source-Commit. Lokale Aenderungen werden als `source_dirty: true` ausgewiesen. Ein Hashmanifest umfasst alle nicht ignorierten Quelldateien; Patch und Liste neuer Dateien werden ebenfalls gespeichert. Die lokale Distribution darf deshalb nicht als unveraenderter Build des Basiscommits ausgegeben werden.

`evidence/installed/installer-smoke.json` bindet den erfolgreichen Installationszyklus an genau die getesteten Setup-Bytes. Die Berichte belegen keine echten Kontowechsel oder OAuth-Abnahme. [Pruefmatrix](verification.md).

## Veroeffentlichungssperre

Ein lokaler Build oder Tag ersetzt die native Produktfreigabe nicht. Der Publish-Job verlangt weiterhin:

- einen erfolgreichen Windows-Build einschliesslich echtem Installer-Smoke-Test;
- die GitHub-Umgebung `release`, die der Betreiber mit erforderlichen Reviewern schuetzen muss;
- `MULTICODEX_RELEASE_ACCEPTANCE` mit einem nativen Bericht fuer exakt denselben Source-Commit und Setup-SHA-256;
- alle Kriterien in `tools/release_gate.py`, insbesondere echte OAuth-Ablaeufe, drei parallele Instanzen, sichere Pool-Uebernahme, DPI/Bedienung, Abhaengigkeiten sowie Lizenz-/Icon-Pruefung.

Diese Gesamtfreigabe liegt weiterhin nicht vor. Sichere Pool-Uebernahme ist noch nicht implementiert. Keine ausgefuellte Freigabe wird erfunden und kein Release-Tag wurde erstellt. Ein spaeteres GitHub Release muss die exakt gepruefte Setup-Datei selbst enthalten.
