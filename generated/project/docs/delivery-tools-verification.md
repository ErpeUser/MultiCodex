# Delivery tools: executed checks and limits

Date: 14 November 2026. Base remote commit:
`0b0c8290de1838217bc2290e2e24c2c854e929e5`.

## Delivered source

The first commit, `cb0e8cb8752ba6f2978658b610060bb6220b04e1`, added the
local Windows runner, exact-build evidence collector, owned-window capture matrix,
regression tests and instructions. The subsequent delivery adds the local Figma
plugin generator/package tests and strengthens native capture to require a
per-monitor-aware window before accepting its measured DPI.

`tools/release_gate.py` and the original application palette were not changed.
No live account, invitation, membership, seat, credential or billing operation was
performed. The private feature branch was updated without force-pushing or merging
to main. These tools do not remove the pre-existing product release blockers.

## Local execution environment

The available host was Linux with Python 3.13.5, Node 22.16.0 and Pillow 12.3.0.
This is **not** the pinned Windows release build environment. The session did not
contain the original working tree, and container network/DNS access could not
retrieve it. A deliberately selective local snapshot was used for the new tools.
The original `ui_tokens.py` and `release_gate.py` bytes were checked against their
remote Git blob hashes. Publications use the full remote tree as the base and
replace only the named changed files, not that partial snapshot.

## Tests run

- `python -m unittest discover -s tests -v`: 35 tests in the locally available
  selective snapshot, 34 passed and 1 skipped. The skipped test needs the actual
  Windows PowerShell parser. This is **not a pass of the full original repository
  suite**; those application/bridge sources were not all present here.
- `node --test tests/figma/renderer.test.cjs`: 9 passed, 0 failed. One of
  the Python tests also invokes these same tests; do not count them twice as
  independent coverage.
- `python -m compileall -q multicodex tools tests`: passed for available sources.
- `node --check plugins/figma/renderer.js` and a generated test package's
  `code.js`: passed.
- `git diff --check`: passed.

The initial tests were run before the missing native collector and Figma renderer/
package builder existed. Further RED/GREEN regressions covered an unsealed build,
replacement of a ready report, unexpected package files and an unrecorded/unaware
DPI context. Temporary real files, hashes, PNG decoding and Git repositories were
used. Figma behavior is exercised through a contract double, never described as a
live canvas. Package tests use an explicitly synthetic plugin ID, never a claim of
registration or ownership.

The evidence collector rejects wrong source or installer bindings, dirty source,
missing reports, truthy non-Boolean ready flags, changed report/image bytes,
duplicate or incomplete image matrices, mismatched native DPI, unsafe filenames,
symlink/reparse paths and malformed/oversized JSON. The machine report always has
`release_ready: false`; every field in its manual-acceptance draft remains false.
A hash index checks consistency, not authenticity or the truth of supplied claims.

## Review findings addressed

A self-review identified that `GetDpiForWindow` alone may return a virtualized DPI
for an unaware/system-aware window. Capture now checks
`GetWindowDpiAwarenessContext` / `GetAwarenessFromDpiAwarenessContext` first and
requires per-monitor awareness. Every frame records that context and the collector
rejects missing, unaware and system-aware contexts. This was regression-tested
before implementation, but the actual Windows API calls were not executed here.

The package verifier also rejects additional files, rather than checking only the
expected files while ignoring unexpected content. The renderer uses editable
layers, current source tokens, awaited fonts and additive pages; generation never
reads application credentials or imports flattened screen images.

Review was performed in the same session. No independent reviewer or fresh
reviewer agent was available; this is not independent review approval.

## Checks that did not run successfully

The original full application/bridge suite, actual Windows build/installer,
PowerShell execution, 96 native display-scale captures, real OAuth and isolated
multi-instance acceptance were **not executed in this environment**. The Windows
and feature-check GitHub check runs for `cb0e8cb` reported failure; no successful
native build is inferred from their creation. The available connector did not
expose the annotations needed to establish the exact early failure cause.

Figma was not edited remotely and no real Figma rendering was observed. The local
plugin is the implemented alternate path; it still requires an assigned plugin
ID and execution/visual inspection in Figma Desktop. No current screenshot,
installer, release URL or completed human acceptance report is fabricated.

Run `tools/verify_native.ps1` on the native host as documented in
`generated/project/docs/native-evidence-runner.md`; build/import the local plugin as documented in
`generated/project/docs/figma/README.md`. All existing release-gate requirements remain binding.

Official DPI reference:
https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getdpiforwindow
