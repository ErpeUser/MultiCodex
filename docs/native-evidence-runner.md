# Native Windows evidence runner

This adds a local route when a hosted Windows job cannot run. It does not issue a
release, grant workspace permissions, or silently accept OAuth/identity tests.
Use a clean Windows test account: the existing installer probe refuses to replace
an already registered MultiCodex installation.

## Execute the real build and first display-scale group

Commit/pull the desired source first. Install the prerequisites documented in
`docs/installation.md`, including PowerShell 7, CPython 3.12.10 x64 and Inno Setup.
Set Windows display scaling to **100 percent** and run from the repository:

```powershell
pwsh -NoProfile -File tools/verify_native.ps1 -Dpi 100
```

The runner checks a clean source tree, moves existing `evidence/` and `output/`
into a newly named temporary backup directory (printed in the console), then
executes the existing locked-dependency/test/bundle/installer build. It does not
remove that backup or touch profiles, sessions or credentials. The installation
probe has its existing own-account and exact-process protections.

After a successful fresh build, `build-index.json` binds the exact bytes of the
runtime, GUI, installation and build reports to the source commit and installer.
A missing or modified report no longer passes merely because it says `ready`.
This is a consistency index, **not a digital signature or independent attestation**.

## Complete the native display matrix

Change the actual Windows display scale and run each command on that display:

```powershell
pwsh -NoProfile -File tools/verify_native.ps1 -CaptureOnly -Dpi 125
pwsh -NoProfile -File tools/verify_native.ps1 -CaptureOnly -Dpi 150
pwsh -NoProfile -File tools/verify_native.ps1 -CaptureOnly -Dpi 200
```

Do not rebuild between these commands: every capture must cover the same source
and installer bytes. The application window's DPI is measured with
`GetDpiForWindow` for every screenshot, after requiring a per-monitor-aware
window via `GetWindowDpiAwarenessContext` / `GetAwarenessFromDpiAwarenessContext`.
An unaware/system-aware window is rejected rather than treated as a 100% proof. A requested/mapped DPI mismatch is an
error; changing Tk scaling does not substitute for a native display change.

Each group captures all six application pages, dark/light and 900x640/1180x760
requested window sizes: **24 images per group, 96 total**. Actual image dimensions
are recorded separately. These are real **source-GUI** captures using a temporary
profile, not packaged-executable screenshots or real account acceptance. Existing
packaged/installed GUI smoke reports are checked separately. Only the owned window
is captured; there is no whole-desktop fallback.

Existing capture folders are never overwritten. A failed run may leave partial
images but no successful manifest. Preserve/move that specific failed group before
retrying it. Do not delete unexplained application state to make a test pass.

## Output and exit codes

The uniquely named `evidence/native-evidence-*.json` reports exact coverage,
report hashes and named missing/invalid checks. Each associated `.DRAFT.json`
contains the commit and installer hash, but **all manual checks remain false**.

- Exit 0: machine-evidence matrix is complete and consistent, not release approval.
- Exit 1: more matrix/check evidence is needed; existing completed groups remain.
- Exit 2 from the collector: invalid bindings, unsafe input or output creation failure.

Real OAuth/re-login/cancellation, three isolated official desktop instances,
keyboard/focus review, secure existing-pool import and other product acceptance
remain subject to `tools/release_gate.py`. Nothing in this runner sets those flags.

The collector can also be invoked explicitly:

```powershell
.venv/Scripts/python.exe tools/native_evidence.py --evidence evidence --setup output/EXACT-SETUP.exe --commit EXACT-COMMIT --captures evidence/native-matrix/dpi-100 --captures evidence/native-matrix/dpi-125 --captures evidence/native-matrix/dpi-150 --captures evidence/native-matrix/dpi-200 --output evidence/new-review.json --draft evidence/new-acceptance.DRAFT.json
```

## Verification of this implementation

The new Python tests exercise actual temporary files, SHA-256 hashes, PNG decoding,
strict JSON, real temporary git repositories, path checks and the unchanged release
gate. They use synthetic build reports/images, not native acceptance evidence.
A separate test invokes the actual PowerShell parser on Windows and is skipped on
non-Windows hosts. The application/installer/DPI run itself must execute on Windows.
