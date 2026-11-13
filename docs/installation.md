# Installation, Windows-Build und Release

## Endbenutzerstatus

Es wurde in dieser Sitzung **keine Windows-Setup-EXE gebaut**, kein Windows-Installer gestartet und kein GitHub Release angelegt. Dieses Dokument beschreibt den vorbereiteten Entwicklungs-/Buildweg, nicht einen bereits verfuegbaren Download.

Ein spaeterer gepruefter Installer soll Python, die GUI und die benoetigte Node-Laufzeit enthalten. Die offizielle Codex-Desktop-Anwendung wird nicht mitgeliefert und nicht veraendert.

## Entwicklungsumgebung

Windows 11 x64; Python 3.12 oder neuer; Node 22.19 oder neuer; die passende offizielle Codex-Desktop-Installation. Das aktuelle Erkennungsmuster ist `OpenAI.Codex_*/app/ChatGPT.exe`. Eine beliebige neue ChatGPT-Version wird nicht als kompatibel ausgegeben.

```powershell
python -m pip install -r requirements-build.txt
npm install --prefix bridge --omit=dev --ignore-scripts --no-audit --no-fund
python -m unittest discover -s tests -v
node --test bridge/tests/service.test.mjs
python run.py --self-check --report runtime-check.json
python run.py --gui-smoke --report gui-check.json
python run.py
```

Die beiden Pruefbefehle liefern Exitcode 1 bei fehlenden Voraussetzungen. Der GUI-Probelauf arbeitet nur mit einem temporaeren Profil. Er prueft echte Widget-Erzeugung, Seiten und zwei Themes/Fenstergroessen, **nicht** den vollstaendigen Bedienungs-, DPI-, OAuth- oder Multi-Window-Ablauf.

Npm-Installationsskripte werden absichtlich nicht ausgefuehrt: der Manager darf nicht schon bei Installation fremde Codex-Konfigurationen oder Launcher umbinden. Ein volles, ueberprueftes transitive-dependency Lockfile fehlt in diesem Snapshot; `npm install` ist daher kein belegter reproduzierbarer Release-Build.

## Windows-Pipeline

`.github/workflows/windows.yml` ist vorbereitet fuer:

1. Python-/Node-Tests und Python-Syntaxpruefung.
2. Echte Runtime- und Widget-Pruefungen.
3. PyInstaller-One-Directory-Build inklusive CustomTkinter-Ressourcen und Python-Distributionshinweisen.
4. Buendelung von `node.exe`, Node-Lizenz und gepinntem Multi-Auth-Paket; keine offiziellen Desktop-Binaries.
5. Paketpruefung mit `Start-Process`, explizitem Warten, Exitcode und JSON-Bericht.
6. Inno-Setup-Compiler vom Runner, dessen Version aufgezeichnet wird. Fehlt er, bricht der Build ab, statt ungeprueft einen anderen Compiler zu installieren.
7. Installation, echter GUI-Start, gleichversioniges Upgrade, Deinstallation und Erhalt einer externen Testdatei durch `tools/installer_smoke.ps1`.
8. Setup-EXE, Buildnachweise und SHA-256-Pruefsummen als private Buildartefakte.

Die YAML-Datei wurde lokal geparst; PowerShell, PyInstaller-Windows-Build und Inno Setup wurden hier **nicht ausgefuehrt**. Signierung und eigenes Anwendungssymbol fehlen. Windows 10 ist nicht getestet. Ein Upgrade zwischen unterschiedlichen Produktversionen ist durch den gleichversionigen Smoke-Test ebenfalls nicht belegt.

## Getrennte Datenspeicherung

Programm: `%LOCALAPPDATA%\Programs\MultiCodex`.

Daten: `%LOCALAPPDATA%\MultiCodex\profiles` und `settings.json`. Die Installationsdateiliste enthaelt diese Daten nicht. Der vorbereitete Installations-Smoke-Test kontrolliert ihren Erhalt; das wurde in dieser Linux-Sitzung nicht nativ nachgewiesen.

Verknuepfte Originalprofile bleiben an ihrem bisherigen Ort. Fuer verwaltete Logins verlangt der Code Keyring-Speicherung; es gibt keine automatische Klartext-Rueckfalloption. Mehr dazu in `security.md`.

## Veroeffentlichungssperre

Ein Tag allein reicht nicht. Der Publish-Job verlangt:

- einen erfolgreichen Windows-Build mit echtem Installer-Smoke-Test;
- die GitHub-Umgebung `release`, die der Betreiber mit erforderlichen Reviewern schuetzen muss;
- eine Variable `MULTICODEX_RELEASE_ACCEPTANCE` mit einem nativen Pruefbericht;
- **exakt passenden Source-Commit und SHA-256 der getesteten Setup-Datei**;
- alle Kriterien in `tools/release_gate.py` ausdruecklich `true`, darunter sichere Uebernahme bestehender Pool-Konten, echte OAuth-Ablaufe, drei parallele Instanzen, DPI, vollstaendige Locks und Lizenz-/Icon-Pruefung.

Diese Voraussetzungen sind jetzt nicht erfuellt. Der Checker prueft Bindung und Vollstaendigkeit des Berichts, nicht die Wahrhaftigkeit eines manuell ausgefuellten Formulars. Native Tester und Reviewer bleiben erforderlich.

Praktischer spaeterer Ablauf: Der Tag-Build erzeugt ein Artefakt; die Veroeffentlichung bleibt gesperrt. Genau dieses Artefakt wird auf einem autorisierten Windows-Testsystem geprueft. Anschliessend wird der Bericht als Variable der geschuetzten Umgebung hinterlegt und nur der fehlgeschlagene Publish-Job erneut ausgefuehrt. So bleibt die Freigabe an dieselben Installer-Bytes gebunden.

Ein erfolgreich veroeffentlichtes Release muss die Setup-Datei selbst enthalten, nicht nur einen Link auf ein kurzlebiges Actions-Artefakt. Aktuell gibt es keinen solchen Release-Link.
