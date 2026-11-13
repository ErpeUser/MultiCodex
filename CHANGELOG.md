# Changelog

## 0.2.0-dev - 2026-11-13

Recovered the exact 0.1.0-dev commit and all 37 archived files; continued its history rather than recreating a disconnected project.

- Added profile-owned, official app-server login slots, staged re-login, identity/persistence verification, selected-instance restart, rollback and explicit interrupted-operation recovery.
- Preserved the previous login as a selectable slot when adding a new one.
- Replaced unsafe global account-selection UI with profile-specific actions. Global multi-auth inventory remains read-only; secure pool credential adoption is still missing.
- Hardened filesystem identities, metadata schemas, reserved/hidden names, catalogue/profile locks, process identity/lifecycle and inherited environment isolation.
- Added bounded worker scheduling, cached GUI snapshots, cancellation, persisted themes and safe error presentation.
- Fixed false-positive self-checks, normalized usage presentation and prepared real-widget/installed-application probes.
- Added a native acceptance gate bound to the exact source commit and installer hash; no release was produced.
- Expanded local coverage to 107 Python and 9 Node tests. Real Windows/OAuth/GUI/installer acceptance remains outstanding.

## 0.1.0-dev

Initial recovered development baseline: 37 files, 21 Python tests and 3 Node tests. Profile catalogue, global account adapter, basic GUI and preliminary Windows build configuration. Not a finished release.
