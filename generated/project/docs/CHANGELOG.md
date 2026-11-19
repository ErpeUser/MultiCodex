# Changelog

## Unreleased - 2026-11-13

- Repaired the official browser sign-in flow: visible Anmelden entry, Codex 1 guidance, retryable browser launch, bounded cancellation, and no false foreground progress during background refresh.

## 0.2.1-dev - 2026-11-13

- Built and installed the updated Windows EXE and Setup; verified packaged runtime/GUI, installer smoke, profile preservation and exact installed executable.
- Propagated cancellation through initial and persistence account reads and added native GUI/transport regressions.

- Built and checked a local Windows 11 x64 development EXE, portable ZIP and Inno Setup installer; verified runtime, actual widgets, installation, same-version upgrade, uninstall and external-data preservation.
- Added a single Windows build command shared with CI, a CPython 3.12.10 x64 dependency lock with wheel hashes, and an npm lock verified with install scripts disabled.
- Fixed cyclic Tk resource cleanup running in background service threads; added a native red/green regression and UI-thread garbage collection.
- Restricted GUI screenshots to the owned temporary test window instead of capturing potentially unrelated foreground desktop contents.
- Bundled official Node 22.19.0 with a pinned archive checksum, Python/Node/dependency notices and retained project licenses. Full OAuth/multi-instance release acceptance remains open.
- Published the complete reviewed source tree to the public `ErpeUser/MultiCodex` default branch.
- Expanded read-only legacy profile discovery to the known local, roaming, user and `.codex/CodexProfiles` roots without recursive or browser-data scanning.
- Prevented login fallback from treating corrupt session catalogues as a missing account identity; added a regression test for the blocked mutation path.

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
