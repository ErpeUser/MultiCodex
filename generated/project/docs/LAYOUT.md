# MultiCodex: source-only repository layout

The checkout keeps **source code at the top level** and all non-code project
material under `generated/`. This split does not imply that every file below
`generated/` is disposable.

## Canonical layout

```text
MultiCodex/
  multicodex/              Python application code
  bridge/                  Node service source and its npm lock manifest
  plugins/figma/           Figma renderer source
  tests/                   Python and Figma contract test source
  tools/                   Build, verification and migration scripts (source)
  packaging/               PyInstaller and Inno Setup source
  run.py                   Application entry point
  generated/
    project/               Versioned documentation, governance, specs, licenses
      docs/
      specifications/
      governance/
      licenses/
      config/python/       Hashed Python build lock + requirements
      config/build/        Windows version metadata
      design/
    runtime/               Generated, ignored work products
      build/
      dist/
      output/              Installer and portable release products; preserve
      evidence/            Historical test and licensing evidence; preserve
      archive/             Preserved older build evidence; preserve
      dependencies/python/venv/
      dependencies/node/node_modules/
      dependencies/toolchains/
      cache/
      downloads/
      logs/
      reports/
      temp/
    local/                 Ignored local tool settings, migration backups
      tool-state/codex/
      migration/
      git/pre-migration-backup/
  .github/workflows/       GitHub-required workflow location
  .gitignore               Root ignore rules required for normal Git
  .git/                    Primary Git repository metadata
```

`generated/project/` is source-controlled and **must not be automatically
deleted**. `generated/runtime/` is ignored but holds irreplaceable release
evidence and rollback packages alongside regenerable caches. Only explicitly
scoped caches and scratch data may be purged automatically. `generated/local/`
must never be committed or uploaded.

### Necessary integration exceptions

- GitHub Actions only discovers versioned workflow definitions under root
  `.github/workflows/`. No mirrored copies are maintained.
- The root `.gitignore` must be readable in a fresh checkout.
- The public checkout uses the repository default branch `main`. Agent work is
  committed directly there. Feature branches and pull requests are not part of
  the normal agent workflow.
- `bridge/package.json` and `bridge/package-lock.json` are required source
  manifests. The **actual** packages live under
  `generated/runtime/dependencies/node/node_modules/`. On Windows,
  `tools/setup_node_deps.ps1` creates a small `bridge/node_modules`
  directory junction for Node ESM resolution. Do not treat that junction as
  a second physical dependency copy.

### Windows source setup

From the project root:

```powershell
py -3.12 -m venv generated/runtime/dependencies/python/venv
$env:PIP_CACHE_DIR = "$PWD/generated/runtime/cache/pip"
& ./generated/runtime/dependencies/python/venv/Scripts/python.exe -m pip install --require-hashes --only-binary=:all: -r generated/project/config/python/requirements-build.windows-x64.lock
./tools/setup_node_deps.ps1
$env:PYTHONPYCACHEPREFIX = "$PWD/generated/runtime/cache/pycache"
$env:RUFF_CACHE_DIR = "$PWD/generated/runtime/cache/ruff"
& ./generated/runtime/dependencies/python/venv/Scripts/python.exe tools/check_references.py
& ./generated/runtime/dependencies/python/venv/Scripts/python.exe -m unittest discover -s tests -q
```

A normal local Ruff invocation should set `RUFF_CACHE_DIR` or pass
`--no-cache` to avoid accidentally generating a root `.ruff_cache/`.
The official Windows build is still `./tools/build_windows.ps1`; it requires
a clean Git source tree, empty build-output directories, and the pinned toolchain.
Do not invoke a real installer/upgrade smoke test against production data.

### Reference and migration tools

- The three completed one-time migration scripts were removed from active
  `tools/` after SHA-256 verification. They are retained locally as an archive
  at `generated/local/migration/one-time-migration-scripts-2026-11-18.zip`.
  The archive is intentionally untracked and is **not** needed by a new clone.
- `tools/cleanup_generated.py`: dry-run-first cleanup with an exact allowlist,
  checked archive hashes, verified validation builds and protection of actual
  installer outputs, source materials, evidence, Git and rollback packages.
  Use `python tools/cleanup_generated.py` to preview and
  `python tools/cleanup_generated.py --apply` only after review. Cleanup reports
  are retained as `generated/runtime/reports/cleanup-*.json`.
  The default groups are `cache`, `validation-build` and `downloads`; actual
  published artifacts under `generated/runtime/output/`, historical evidence,
  native acceptance, user profiles and the rollback bundle are never targets.
  The cleanup utility refuses unverified build results and linked paths.
- `tools/setup_node_deps.ps1`: locked npm install into central dependencies.
- `tools/check_references.py`: fast, read-only internal Markdown link check.
  Called from Windows build, GitHub CI, and a regression test.
- `tests/test_generated_layout.py`: verifies top-level layout, canonical
  source references, Git ignore contracts, and current documentation links.

### Redundancy audit (18 November 2026)

- Byte-identical maintained source files: none in the examined source set.
- `jscpd`: zero clones across 126 source/test files at 12 lines / 95 tokens.
  A more sensitive scan detected only two short patterns: distinct SQLite
  schema initializers and independent linked-path security checks. Both are
  intentionally kept separate to preserve transaction and error semantics.
- Build copies of Python libraries and the duplicate SBOM in
  `output/`/`evidence/` are needed for independently auditable deliverables;
  they are not safe cleanup targets.
- The generated PyInstaller intermediate/distribution, downloaded archives,
  pinned Python virtualenv, installed Node packages and portable test toolchains
  have been purged after verification. They can be reconstructed from the
  versioned Python/npm locks and the documented tool versions; none are needed
  to run the already installed Windows application. The Node junction
  `bridge/node_modules` was detached before deleting its target. Rerun the
  setup commands above before executing source-level Python or Node tests.
- Cleanup was completed on 18 November 2026. Its non-regenerable integrity
  record is retained locally at
  `generated/local/migration/reconstructible-purge-2026-11-18.json`.
  Historical release evidence, the installer, portable package, rollback bundle,
  primary Git metadata and recovery copies were deliberately preserved.

No user profile, OAuth secrets, desktop app install, remote branch, release, or
external worktree source files are part of the directory migration. A successful
synthetic test suite does not imply native OAuth/multi-instance acceptance.
