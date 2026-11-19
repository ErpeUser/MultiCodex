# Contributing

This is an unreleased development branch, not an accepted Windows product.

Read AGENTS.md, DESIGN.md, UX-CONTRACT.md, generated/project/docs/security.md and generated/project/docs/verification.md. Preserve the original commit history. Use temporary fixtures, never personal auth files, in tests or CI.

Run the complete suites before committing:

```powershell
python -m unittest discover -s tests -v
node --test bridge/tests/service.test.mjs
python -m compileall -q multicodex tools run.py
```

Add a failing regression before changing safety behavior. Global account pinning is not per-instance mapping. Do not reintroduce manager CLI first-use effects, file-mode token export, automatic force-kills or plaintext auth fallback.

A green unit-test suite is not native acceptance. Record actual Windows/CLI/Desktop versions, real GUI/DPI behavior, OAuth results and installer hash before proposing a release. An independent review is still required; the current recovery pass received only a self-review.

Do not delete unexplained session homes, damaged metadata or recovery journals automatically. Define a reversible, credential-safe migration and its tests before changing an existing user's storage.
