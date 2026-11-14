# Delivery tools implementation plan

> **For agentic workers:** Use superpowers:executing-plans task by task.

**Goal:** Complete the previously announced local Figma plugin and native Windows evidence path without replacing the application or weakening release gates.
**Architecture:** Add dependency-free local plugin generation and an evidence collector around existing native scripts. Reuse ui_tokens.py and release_gate.REQUIRED_CHECKS.
**Tech stack:** Python 3.12, Node 22 built-in tests, Figma Plugin API, Windows PowerShell 7.
**Spec:** AGENTS.md, DESIGN.md, UX-CONTRACT.md, docs/verification.md at remote 0b0c829.

## Global constraints
- Preserve original source, user sessions, credentials and private repository status.
- No fabricated native pass, screenshot, Figma edit or provider mutation.
- Never promote machine checks to human OAuth/multi-instance acceptance.
- New files only except documented build/CI integration; no force push.

## Review focus
- Stale, duplicate, missing or wrong-commit evidence must not pass.
- Paths, links and raw provider data must not enter evidence exports.
- Failed or repeated Figma generation must preserve existing user edits.
- All six pages and both themes must be represented in the plugin.
- Offline/restricted environments must produce an explicit blocker, not a success.

### Task 1: Native evidence and capture path
**Files:** tools/native_evidence.py, tools/capture_native_matrix.py, tests/test_native_evidence.py, tools/verify_native.ps1.
**Consumes:** release_gate.REQUIRED_CHECKS, existing build_windows.ps1 and capture_gui_screenshots.settle.
**Produces:** strict per-build matrix evidence and a never-auto-approved acceptance draft.
- [x] Write failing tests: exact source/setup binding, complete 96-image matrix, duplicate/missing/corrupt captures, path/link rejection, false-vs-truthy readiness, unchanged manual gate.
- [x] Run `python -m unittest discover -s tests -p test_native_evidence.py -v`; expect RED.
- [x] Implement collection and native capture; actual host DPI must be measured, not simulated.
- [x] Repeat command; expect GREEN. Run complete locally available suite, record its scope.
- [x] Publish additive commit against expected remote head.

### Task 2: Local Figma plugin
**Files:** design/figma/*, tools/build_figma_plugin.py, tests/test_figma_package.py.
**Consumes:** application THEMES and NAV_WIDTH.
**Produces:** importable local plugin with editable six-page dark/light design references and no network access.
- [x] Write failing Node tests for six pages x two themes, font preflight, additive repeat runs, error cleanup, theme tokens, no credential access.
- [x] Write package tests that reject stale generated source and require explicit real Figma plugin id.
- [x] Implement using only standard documented Figma API.
- [x] Run Node tests, Python suite, syntax checks; distinguish contract-double tests from live Figma validation.
- [x] Publish additive commit and usage/verification notes.

## Execution record

Task 1 was published as `cb0e8cb8752ba6f2978658b610060bb6220b04e1`. Task 2 and
the DPI-awareness regression are published together with this updated plan.
Implementation/tests are complete for these delivery tools, not native product
acceptance. The locally available suite covers a selective snapshot; the original
full suite, Windows execution and live Figma inspection remain unverified. See
`docs/delivery-tools-verification.md` for exact commands, results and scope.
