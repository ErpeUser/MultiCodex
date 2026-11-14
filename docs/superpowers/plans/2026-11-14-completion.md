# MultiCodex completion implementation plan

> **For agentic workers:** Use superpowers:executing-plans. Publish independently checked work packages throughout execution, not only at the end.

**Goal:** Complete supported workspace administration, redesign all six native views, and make design/native verification reproducible without weakening existing safety boundaries.

**Architecture:** Preserve Python 3.12+, CustomTkinter, the existing worker boundary, official Codex authentication, profile isolation and credential-free SQLite quota history. Separate administrative operations from quota monitoring and profile activation. Use explicit provider capabilities and read-back verification; unsupported operations remain blocked, never simulated.

**Tech Stack:** Python standard library, Tk/CustomTkinter, SQLite, existing Node bridge, GitHub Actions and Figma Plugin API.

**Spec:** User-supplied MultiCodex implementation specification, sections 4, 12-14 and 19-21; AGENTS.md, DESIGN.md, UX-CONTRACT.md and docs/security.md.

## Global constraints

- Target main; no force push, public mirror, credential migration, release tag or production account test.
- Preserve existing feature commits and new remote changes.
- Never trigger workspace administration from quota exhaustion or a predicted reset.
- Persist a quota snapshot before authorized access removal; invitation is not acceptance.
- No secrets or raw provider responses in persistence, diagnostics, Figma or GitHub.
- Only real Windows execution can produce native Windows acceptance.

## Review focus

- Unknown write outcome must not cause duplicate invitations or repeated removal.
- Concurrent membership changes and the last owner must fail closed.
- Missing role, seat, membership or API capability must remain unknown, not default to permission.
- UI rebuilds and worker completion must preserve Tk-thread ownership.
- Screenshots must capture only the test application, never unrelated desktop windows.

## Task 1 - Workspace administration

Files: multicodex/workspace_admin.py, multicodex/workspace_operations.py, tests/test_workspace_admin.py, tests/test_workspace_operations.py, docs/workspace-administration.md.

- [ ] Verify published ChatGPT Admin API methods, bodies, scopes and response schemas. Keep API Platform and SCIM distinct.
- [ ] Add failing contract, permission, snapshot, owner-protection, idempotency and uncertain-outcome tests.
- [ ] Implement bounded read/write transport, explicit administration requests, persistent operation journal and postcondition verification. No unattended productive tests.
- [ ] Run tests and compilation; review diff and publish a separate commit.

## Task 2 - Six-view native redesign

Files: multicodex/desktop_views.py, multicodex/gui.py, multicodex/ui_tokens.py, tests/test_desktop_views.py, tools/capture_redesign.py, DESIGN.md.

- [ ] Inspect Better Design and current design references; retain MultiCodex palettes and native toolkit.
- [ ] Add failing tests for account search/filter/sort, unknown values, cached quotas, callbacks and all six pages.
- [ ] Implement overview, accounts, instances, usage, diagnostics and settings with reusable native components and existing backend actions.
- [ ] Render dark/light and compact/normal fixtures; inspect and correct clipping. Publish checked changes.

## Task 3 - Editable Figma handoff

Files: design/figma/, tools/export_design.py, tests/test_design_export.py.

- [ ] Attempt the installed Figma integration for the existing file. If no callable connection is exposed, record that exact limitation.
- [ ] Provide a deterministic, non-destructive editable design import with shared runtime tokens, all six pages, dark/light variants and explicit sample-data labels.
- [ ] Test generator and Plugin API structure; do not claim a live Figma edit without returned node IDs.
- [ ] Publish separately.

## Task 4 - Native verification and final integration

Files: tools/native_acceptance.py, tools/verify_windows.ps1, .github/workflows/native-verification.yml, tests/test_native_acceptance.py, docs/completion-verification.md.

- [ ] Add failing tests for evidence provenance, completeness, source binding and refusal of non-Windows acceptance.
- [ ] Implement real-window capture, DPI/theme/size matrix and repeatable Windows verification without real accounts. Preserve the separate real OAuth/instance acceptance gate.
- [ ] Provide hosted and explicitly selected self-hosted Windows runner paths without altering billing or repository visibility.
- [ ] Run every available suite and compile check, review all changes, publish and read back remote HEAD/CI.
- [ ] Report actual results and external blockers; never convert prepared checks into claimed execution.

## Initial observations

main was bd532520a29e0848676e2b864c0fd7a6b4a5d510 and was not branch-protected. Previous feature work remains at 0915fbb4e0f8b742feaf3ca067dcdc6c4ebb5415. GitHub API access works; direct Git network access in this execution environment does not. Current public ChatGPT Admin API documentation lists workspace invitation and user write operations; their exact contracts still require inspection before enabling them.
