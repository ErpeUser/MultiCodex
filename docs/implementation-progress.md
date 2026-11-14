# MultiCodex implementation progress

- Repository: `ErpeUser/MultiCodex` (private)
- Branch: `main`
- Current HEAD: `c4741379c76b7a53a6ff9767b9228295976bfc85` (pushed and verified against `origin/main`).
- Machine-readable register: [`docs/implementation-status.json`](implementation-status.json).

## Current main verification (2026-11-14)

The historical 157-step register below remains the audit baseline. The current
`main` checkout has since been verified with:

- Python: 526 tests passed, 11 host-dependent tests skipped.
- Node bridge: 8 tests passed, 1 host-dependent test skipped.
- Python compileall and whitespace checks passed.
- GUI smoke: all 12 views rendered in dark/light themes at 900x640 and 1180x760.
- GitHub: only `main` remains; no open pull requests; `main` matches `origin/main`.

External acceptance gates remain open where the register requires real Windows
installer evidence, native DPI captures, live OAuth/provider access, Figma
mutation evidence, or live workspace mutations.

This is the exact 157-step execution record from the attached contract. Historical results are labelled; no CI, Windows, OAuth, Figma, admin-mutation, or release acceptance is claimed without evidence.

## Status counts

| Status | Count |
|---|---:|
| `BEREITS_VERIFIZIERT` | 2 |
| `IMPLEMENTIERT_ABNAHME_OFFEN` | 128 |
| `BLOCKIERT_EXTERN` | 26 |
| `OFFEN` | 1 |

The counts sum to 157. Full required fields are in `implementation-status.json`.

## Steps 001–157

| ID | Titel | Status | Checked source |
|---:|---|---|---|
| 001 | GitHub-Basis prüfen | BEREITS_VERIFIZIERT | GitHub metadata; AGENTS.md; workflows |
| 002 | Projektregeln auswerten | BEREITS_VERIFIZIERT | GitHub metadata; AGENTS.md; workflows |
| 003 | Bestehende Funktionen inventarisieren | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 004 | Vollständige Testsuite ausführen | BLOCKIERT_EXTERN | quota*.py; tests/test_quota*.py |
| 005 | GitHub-Actions-Fehler untersuchen | BLOCKIERT_EXTERN | quota*.py; tests/test_quota*.py |
| 006 | CI-Konfiguration korrigieren | BLOCKIERT_EXTERN | quota*.py; tests/test_quota*.py |
| 007 | Abhängigkeiten absichern | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 008 | Fortschrittsprotokoll im Repository | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 009 | Account-ID statt E-Mail als Primäridentität | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 010 | Workspace-Zuordnung absichern | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 011 | Fehlende Workspace-Filter absichern | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 012 | Seat-Berechtigung separat prüfen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 013 | Multi-Workspace-Accounts absichern | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 014 | Kontextänderungen während API-Aufrufen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 015 | Snapshot vor Mitgliederentfernung | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 016 | Snapshot vor Seat-Entzug | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 017 | Snapshot vor Rollenentzug | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 018 | Snapshot-Identität validieren | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 019 | Unbekannten Workspace nicht per E-Mail übernehmen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 020 | Externe Statusänderungen berücksichtigen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 021 | Nach Wiederaufnahme verifizieren | OFFEN | quota*.py; tests/test_quota*.py |
| 022 | Protokollversion erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 023 | Fünf-Stunden-Fenster korrekt zuordnen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 024 | Wochenfenster korrekt zuordnen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 025 | Fehlende Zeitfenster | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 026 | Mehrere Quota-Buckets | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 027 | Codex-Bucket erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 028 | Zusätzliche Buckets behandeln | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 029 | Rate-Limit-Gründe korrigieren | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 030 | `ordinaryUsageAllowed` | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 031 | Spend-Control-Limits | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 032 | Reset-Credits | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 033 | Credits historisieren | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 034 | Planwechsel erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 035 | Seat-Wechsel erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 036 | Fehlerhafte Providerwerte validieren | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 037 | Vollständige Protokolltests | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 038 | Quota-Datenmodell vervollständigen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 039 | Account-Modell vervollständigen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 040 | Quota-Historie erhalten | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 041 | Separate Reset-Zeitpunkte | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 042 | Offline-Reset-Prognose | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 043 | Reset-Zustände ergänzen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 044 | Neue Daten korrigieren Prognosen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 045 | SQLite-Schemamigration | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 046 | Sichere Backups | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 047 | Beschädigte Daten wiederherstellen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 048 | Parallele Speicherzugriffe | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 049 | Bestehenden Quota-Monitor prüfen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 050 | Prüfintervalle | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 051 | Warnschwellen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 052 | Beide Limits berücksichtigen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 053 | Aktuelle Daten erzwingen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 054 | Backoff und Retry | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 055 | Fehlende Berechtigung | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 056 | Authentifizierungsfehler | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 057 | Monitoring nach Neustart | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 058 | In-App-Benachrichtigungen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 059 | Windows-Benachrichtigungen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 060 | Benachrichtigungseinstellungen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 061 | Monitoring-Tests vervollständigen | IMPLEMENTIERT_ABNAHME_OFFEN | quota*.py; tests/test_quota*.py |
| 062 | Kandidatenmodell prüfen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 063 | Workspace und Seat in Kandidatenprüfung | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 064 | Beide Quota-Fenster berücksichtigen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 065 | Provider-Sperren berücksichtigen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 066 | Kandidaten deterministisch sortieren | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 067 | Automatische Kandidatenauswahl | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 068 | Keine Kandidaten vorhanden | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 069 | Reset-Zeitpunkt erreicht | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 070 | Bestehende Zielinstanz erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 071 | Passende Instanz wiederverwenden | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 072 | Fenster gezielt fokussieren | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 073 | Zielinstanz sicher starten | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 074 | Andere Instanzen schützen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 075 | Laufende Arbeiten schützen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 076 | Sessionidentität prüfen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 077 | Live-Instanzzuordnung stärken | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 078 | Falsche Identität erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 079 | Aktivierungsjournal vervollständigen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 080 | Zustandmaschine vervollständigen | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 081 | Crash-Recovery | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 082 | Doppelte Aktionen verhindern | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 083 | Automatik vollständig abschaltbar | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 084 | Profilmanagement-End-to-End-Tests | IMPLEMENTIERT_ABNAHME_OFFEN | profile_activation.py; controller.py; tests/test_profile_activation.py |
| 085 | Aktuelle Admin-Dokumentation prüfen | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 086 | Aktuellen OpenAPI-Vertrag laden | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 087 | Admin-Fähigkeiten dynamisch erkennen | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 088 | Business-Kompatibilität prüfen | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 089 | Enterprise-/Edu-Unterstützung | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 090 | SCIM-Kompatibilität | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 091 | Mitgliederverzeichnis | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 092 | Einladungsverzeichnis | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 093 | Rolleninformationen | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 094 | Seat-Informationen | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 095 | Seat-Verfügbarkeit | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 096 | Workspace-Account-Zuordnung | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 097 | Einladung erstellen | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 098 | Einladung erneut senden | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 099 | Einladung widerrufen | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 100 | Einladung annehmen lassen | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 101 | Mitgliedschaft nach Annahme prüfen | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 102 | Rolle ändern | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 103 | Seat ändern | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 104 | Mitglied entfernen | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 105 | Mitglied wieder aufnehmen | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 106 | Codex-Zugang nach Wiederaufnahme | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 107 | Zusammenhängenden Verwaltungsworkflow | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 108 | Owner-Schutz | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 109 | Administrative Vorschau | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 110 | Exakte Freigabe | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 111 | Idempotenz und Doppelaktionsschutz | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 112 | Readback und unbekannte Ergebnisse | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 113 | Vollständiges Operationsjournal | IMPLEMENTIERT_ABNAHME_OFFEN | workspace*.py; tests/test_workspace*.py |
| 114 | Workspace-Gesamttests | BLOCKIERT_EXTERN | workspace*.py; tests/test_workspace*.py |
| 115 | Gemeinsame GUI-Komponenten | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 116 | Dashboard: Accountzahlen | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 117 | Dashboard: Instanzen | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 118 | Dashboard: Workspace | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 119 | Dashboard: Quotas | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 120 | Dashboard: Resettermine | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 121 | Dashboard: Aufgaben und Fehler | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 122 | Accounttabelle vervollständigen | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 123 | Accounttabelle: Quotas | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 124 | Accounttabelle: Bedienung | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 125 | Accountaktionen | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 126 | Instanzverwaltung | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 127 | Quota-Übersicht | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 128 | Quota-Historie | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 129 | Zusätzliche Quotas und Credits | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 130 | Startwarteschlange | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 131 | Automatik-Einstellungen | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 132 | Idle-Policy | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 133 | Benachrichtigungseinstellungen | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 134 | Workspace-Administrations-GUI | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 135 | Diagnose | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 136 | Recovery-GUI | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 137 | Fehler-/Leer-/Ladezustände | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 138 | GUI-Regressionstests | IMPLEMENTIERT_ABNAHME_OFFEN | gui.py; *ui.py; tests/test_*ui*.py |
| 139 | Bestehendes Design analysieren | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 140 | Better Design verwenden | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 141 | awesome-design-md verwenden | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 142 | Aktuelle Screenshots recherchieren | BLOCKIERT_EXTERN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 143 | Design-Tokens vereinheitlichen | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 144 | Dark Mode fertigstellen | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 145 | Light Mode fertigstellen | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 146 | Tastatur und Accessibility | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 147 | Skalierung und lange Inhalte | IMPLEMENTIERT_ABNAHME_OFFEN | DESIGN.md; UX-CONTRACT.md; .better-design/* |
| 148 | Vorhandene Figma-Datei öffnen | BLOCKIERT_EXTERN | design/figma/*; tests/test_figma_package.py |
| 149 | Editierbare Figma-Ansichten | BLOCKIERT_EXTERN | design/figma/*; tests/test_figma_package.py |
| 150 | Figma-Zustandsvarianten | BLOCKIERT_EXTERN | design/figma/*; tests/test_figma_package.py |
| 151 | Reales Figma-Ergebnis verifizieren | BLOCKIERT_EXTERN | design/figma/*; tests/test_figma_package.py |
| 152 | Figma und echte GUI vergleichen | BLOCKIERT_EXTERN | design/figma/*; tests/test_figma_package.py |
| 153 | Vollständige Windows-Tests | BLOCKIERT_EXTERN | build_windows.ps1; verify_native.ps1; workflows |
| 154 | Native GUI-Abnahme | BLOCKIERT_EXTERN | build_windows.ps1; verify_native.ps1; workflows |
| 155 | Windows-DPI-Matrix | BLOCKIERT_EXTERN | build_windows.ps1; verify_native.ps1; workflows |
| 156 | Echter Login- und Multi-Instanz-Test | BLOCKIERT_EXTERN | build_windows.ps1; verify_native.ps1; workflows |
| 157 | Installer, CI und endgültige Verifikation | BLOCKIERT_EXTERN | build_windows.ps1; verify_native.ps1; workflows |

## Pflichtfehlerfälle (23)

| # | Fehlerfall | Testnachweis | Status |
|---:|---|---|---|
| 001 | Codex app-server unreachable | historical targeted test: test_quota_monitor.MonitorTests.test_backoff_and_retry_exhaustion_are_persistent | IMPLEMENTIERT_ABNAHME_OFFEN |
| 002 | Five-hour or weekly limit missing | historical targeted test: test_quota.QuotaViewTests.test_unknown_window_blocks_but_explicit_null_is_not_invented | IMPLEMENTIERT_ABNAHME_OFFEN |
| 003 | Reset timestamp missing | historical targeted test: test_quota.QuotaViewTests.test_missing_reset_requires_verification | IMPLEMENTIERT_ABNAHME_OFFEN |
| 004 | Provider response damaged or stale | historical quota/provider test suites documented in docs/continuation-verification.md | IMPLEMENTIERT_ABNAHME_OFFEN |
| 005 | Workspace access removed | historical targeted test: test_removed_accounts_keep_snapshot_without_network_probes | IMPLEMENTIERT_ABNAHME_OFFEN |
| 006 | Session or cookies invalid | historical targeted monitor/sign-in tests; real OAuth not run | IMPLEMENTIERT_ABNAHME_OFFEN |
| 007 | Official login failed | historical sign-in/activation tests; real OAuth not run | IMPLEMENTIERT_ABNAHME_OFFEN |
| 008 | Wrong account identity | historical targeted test: test_wrong_identity_does_not_persist_quota | IMPLEMENTIERT_ABNAHME_OFFEN |
| 009 | Seat missing or membership unconfirmed | historical workspace tests; external directory not exercised | IMPLEMENTIERT_ABNAHME_OFFEN |
| 010 | Invitation failed or expired | no current executable admin mutation test; mutation gate remains open | BLOCKIERT_EXTERN |
| 011 | Role change not allowed | historical admin contract/security tests; no live admin mutation | IMPLEMENTIERT_ABNAHME_OFFEN |
| 012 | Sole owner affected | historical security test; external acceptance open | BLOCKIERT_EXTERN |
| 013 | Target instance does not start | historical activation/process tests; native Windows start not run | IMPLEMENTIERT_ABNAHME_OFFEN |
| 014 | Origin instance cannot be safely stopped | historical process identity tests; native acceptance open | IMPLEMENTIERT_ABNAHME_OFFEN |
| 015 | Multiple parallel instances | historical process lifecycle tests; three real instances not run | IMPLEMENTIERT_ABNAHME_OFFEN |
| 016 | Concurrent automation actions | historical lock/activation tests | IMPLEMENTIERT_ABNAHME_OFFEN |
| 017 | Crash during storage or switch | historical recovery tests; native crash injection not run | IMPLEMENTIERT_ABNAHME_OFFEN |
| 018 | Corrupted quota history | historical quota store/restore tests; current full suite not runnable | IMPLEMENTIERT_ABNAHME_OFFEN |
| 019 | Reset timestamp changes | historical quota tests | IMPLEMENTIERT_ABNAHME_OFFEN |
| 020 | Restoration with a different seat | historical workspace/quota tests; external seat change not run | IMPLEMENTIERT_ABNAHME_OFFEN |
| 021 | Quota remains exhausted after expected reset | historical test: test_reset_boundary_is_forecast_and_keeps_last_usage | IMPLEMENTIERT_ABNAHME_OFFEN |
| 022 | Unexpected provider reset | historical provider/quota tests; live provider not run | BLOCKIERT_EXTERN |
| 023 | Backend and GUI state disagree | historical UI/service tests; full application GUI acceptance open | BLOCKIERT_EXTERN |

## Current external blockers

- Full credentialed checkout and current full Python/Node/GUI rerun unavailable.
- Latest feature run `43646780333` and Windows run `43646780325` failed before job steps with `runner_id: 0`; publish job skipped.
- Windows DPI/installer, OAuth/re-login, three-instance, Figma round-trip, and external workspace-admin mutation evidence remain open.
- Step 021 is the next technical slice once an authorized checkout or equivalent source export is available.
