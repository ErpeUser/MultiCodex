# MultiCodex – Superpowers-Quellcodeaudit (18. November 2026)

## Zweck und Geltungsbereich

Lokales Windows-Quellcodeaudit nach der physischen Bereinigung. Diese Datei dokumentiert ausgeführte Prüfungen, unterscheidet Quellcode-/Testnachweise von echter Produktabnahme und erteilt **keine Release-Freigabe**.

- Arbeitszweig: `codex/windows-hardening-20261115`
- Basis-HEAD während der Prüfung: `4f22f0ba8f4345dbc634ca4e867d28de074b0cb1`
- Stand von `origin/main` zu Beginn: `f5f516e` (16. November 2026). Die Zweige sind verschieden; die aktuellen Änderungen sind nicht auf GitHub.
- Vorher vorhandene Änderungen (inkl. historischer Dateilöschungen und `docs/implementation-status.json`) wurden nicht zurückgesetzt; weder ein Commit noch Push, Merge, Tag oder Release wurde erstellt.
- Quellen: aktueller lokaler Arbeitsbaum, `AGENTS.md`, Git-Historie, offizielle GitHub-Actions-Protokolle der Läufe 43860624363 / 43860623998 (16. November 2026).

## Tatsächliche Änderungen dieser Prüfrunde

1. **Privatsichtbarkeit vor Veröffentlichung:** `.github/workflows/windows.yml` bindet die Veröffentlichung an `github.event.repository.private == true` und übergibt diesen Wert an `tools/release_gate.py`. Die Release-CLI verweigert in GitHub Actions fehlende oder falsche Sichtbarkeitsbestätigung. Drei gezielte Tests prüfen public/fehlend/private mit weiterhin fehlender nativer Abnahme. Die bestehende Bindung an Commit, Installer, SBOM und Lizenzreview bleibt unverändert.
2. **Windows-8.3-Aliase:** `multicodex/processes.py` kanonisiert lokale absolute Windows-Pfade vor der exakten Zuordnung. Ein vorher fehlschlagender Regressionstest mit `C:\PROGRA~1` und `C:\Program Files` ist grün; ähnlich benannte Fremdprofile bleiben ausgeschlossen. Netzwerkpfade werden nicht aufgelöst. Starttests vergleichen echte Pfadidentität statt identische Schreibweisen.
3. **CI-Zweigabdeckung:** `.github/workflows/feature-checks.yml` berücksichtigt bei Pushes auch `codex/**`. Ein Distributionstest prüft die erforderlichen Muster unabhängig von ihrer Reihenfolge.
4. **Anforderungsinventur:** `docs/implementation-status.json` enthält 157 nummerierte Einträge und 23 Fehlerfälle. Der vorbestehende widersprüchliche Zähler `count: 155` wurde auf 157 korrigiert; drei neue Tests sichern die Metadaten und fortlaufende IDs. Statusfelder gelten weiterhin ausdrücklich als **historisch**, nicht als aktuelle native Abnahme.
5. **Statische Bereinigung:** Zwölf unbenutzte Test-Imports, eine unbenutzte Testvariable, eine Closure-Bindung in der GUI-Shutdown-Probe, ein collections.abc-Import und eine überholte Typannotation wurden bereinigt. Die älteren Quellcode-Löschungen bleiben im Arbeitsbaum erhalten.

## Unmittelbare Testnachweise

- Vollständige Python-`unittest`-Suite: **639 ausgeführt, 627 bestanden, 12 übersprungen, 0 fehlgeschlagen, Exitcode 0**. Verifiziert mit Python 3.12.10 und temporärer, offizieller PowerShell 7.7.0 x64. Die PowerShell-Archiv-SHA-256 wurde mit dem vom PowerShell-Projekt veröffentlichten Wert `7c74e03b20a75b59715847439d046a6214b1863ee79b187872980f139bb4a05f` verglichen.
- Node-Bridge: **9 bestanden, 1 übersprungen**, Node 22.23.5; Figma-Renderer: **9 bestanden, 0 übersprungen**.
- Ruff (F401, F841, B007, B023, UP035, UP037): keine Befunde in den gescannten Projekt- und Testdateien; Python-Kompilierung und YAML-Syntaxprüfung bestanden.
- `pip check`: keine defekten Abhängigkeiten. `pip-audit`: keine bekannten Schwachstellen für 11 erfasste Lock-Pakete. `npm audit --omit=dev`: 0 bekannte Schwachstellen.
- Bandit: 0 Hinweise mittlerer oder hoher, 16 niedrige Hinweise (u. a. absichtliche, shellfreie Subprozesse und optionale Fensterfokussierung). Die Hinweise sind keine pauschalen Fehlernachweise.
- Quellcode-Self-Check und GUI-Smoke, installierte EXE-Self-Check und GUI-Smoke wurden zusätzlich zur Testsuite separat ausgeführt; sie sind synthetische Laufzeitprüfungen und keine echte Konto-/Desktop-Abnahme.

## Sicherheits- und Dokumentationsprüfung

- `ErpeUser/MultiCodex` meldete GitHub am Prüfungstag als **öffentlich**; `AGENTS.md` und `README.md` verlangen ein **privates** Repository. Die GitHub-Sichtbarkeit wurde **nicht** verändert. Die zusätzliche lokale Release-Sperre ist bis zum Push nicht wirksam.
- Im lokalen Git-Verlauf: 137 erreichbare Commits; keine Pfade mit den ausdrücklich verbotenen Credential-Dateinamen und keine Treffer für die untersuchten üblichen Private-Key-/Token-Präfixmuster. Dies ist **keine** vollständige forensische Geheimnisprüfung.
- Keine vorhandenen GitHub-Releases in der abgefragten Release-Liste. Zuletzt eingesehene GitHub-CI-Läufe vom 16. November waren fehlerhaft: Feature-Suite bei mehreren Windows-/GUI-/Sitzungstests; Installer-Build bei PE-Versionsanzeige `0.0.0`. Lokal liefert `tools/compiler_identity.py` die tatsächliche Inno-Version `6.7.3`. Die aktuelle lokale Prüfung ist kein neuer CI-Lauf.
- Relative Markdown-Links aller damals vorhandenen versionierten Markdown-Dateien ohne fehlenden Zielpfad geprüft.
- Installierte EXE, vorhandener Installer, Rollback-Bundle, `evidence/`, externe Benutzerverzeichnisse und Zugangsdaten wurden nicht gelöscht.

## Offene Grenzen / unveränderte Freigabesperren

- Kein vollständiger reproduzierbarer Neubuild aus einem sauberen, festgeschriebenen Quellcommit. Das Buildskript fordert einen sauberen Arbeitsbaum und leere Artefaktverzeichnisse; die vorbestehenden Benutzeränderungen und Nachweise wurden nicht für einen Build gelöscht.
- Keine echte OAuth-/Windows-Credential-Manager-Abnahme, kein echtes Hinzufügen mehrerer Konten, keine drei parallelen offiziellen Desktop-Instanzen unter echten Profilen und keine native DPI-/Tastatur-/Upgrade-Matrix.
- Keine verifizierte Übernahme globaler Pool-Credentials in geschützte native Profile; keine Workarounds am Authentifizierungsspeicher.
- Offene Projektanforderungen in der historischen Statusdatei werden durch diese lokale Prüfung **nicht** automatisch zu `BEREITS_VERIFIZIERT`.
- Ohne ausdrücklich freigegebenen GitHub-Sichtbarkeitswechsel, einen Commit/Push, einen erfolgreichen Windows-CI-Lauf und die vollständige native Abnahme ist keine öffentliche oder private Veröffentlichung freigegeben.

**Integrität:** Die umfangreiche lokale Bereinigung und die früher bereits geänderte Statusdatei wurden nicht als eigener Commit ausgegeben. Die nach der Prüfung temporär installierten Testwerkzeuge sollen vor Abschluss wieder aus dem Projekt entfernt werden.
