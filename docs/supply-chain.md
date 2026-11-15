# Bundle inventory and license review

`tools/build_windows.ps1` creates a CycloneDX 1.6 post-build inventory,
`SBOM.cdx.json`, and a machine-readable `license-report.json` in the bundle,
`evidence/` and `output/`. Both files are shipped inside the installer/portable
archive. Their exact hashes and the source commit are recorded in `build.json`.

The inventory reads the **shipped** Python distribution metadata and npm package
metadata, including nested bundled packages and vendored source copies. It
compares versions with the full Python and npm locks. A bundled npm dependency
without its own registry hash records the enclosing verified tarball's integrity
as inherited provenance. Every shipped file has a SHA-256 file component; the
inventory excludes its two generated files to avoid circular hashes. Python
wheel hashes identify locked acquisition artifacts; they do not assert that
compiled PYZ modules are byte-for-byte wheels. Python distribution metadata can
also cover build components, such as the shipped PyInstaller bootloader notices.
Dependency relationships reflect declared package metadata and the physically
present dependencies; Python optional markers are not claimed as runtime traces.

The Python and Node runtime versions, Node archive URL/hash and retained notice
paths are recorded. Native `.dll`, `.pyd` and `.exe` files are individually hashed
and flagged for attribution review. Their version/license is not guessed from
the filename. Aggregate CPython/Node notices also require review because their
contents include several upstream components. The generator deliberately does
not equate a metadata license declaration with completed legal review.

Missing metadata/versions/integrity, unmatched packages, unfamiliar license
expressions and missing license texts produce explicit blockers. The default
command still permits a development installer containing the unresolved report.
`--strict` makes any blocker fail the inventory command. Neither mode produces a
native acceptance report or changes any release criterion.

## Review an exact build

The release command additionally requires:

```powershell
python tools/release_gate.py --commit <commit> --setup <setup.exe> --sbom output/SBOM.cdx.json --license-report output/license-report.json
```

The existing `MULTICODEX_RELEASE_ACCEPTANCE` JSON must include `sbom_sha256` and
`license_report_sha256` as well as its existing exact installer/source bindings,
reviewer, recent timestamp and all native checks. `native_evidence.py` copies
these hashes into an **unapproved** draft only after checking the evidence files
against the build manifest. Old evidence without inventory hashes cannot pass
the release command.

A qualified reviewer must resolve each license-only blocker individually in a
`license_review` array in that same acceptance JSON. Each object contains:

- `blocker`: one exact blocker string from the generated report;
- `reviewer`: the same named reviewer as the native acceptance report;
- `license_expression`: an expression admitted by `REVIEWED_EXPRESSIONS` in
  `tools/supply_chain.py` after checking applicability to this component;
- `notice`: the relative path of the applicable notice **actually shipped and
  inventoried** in the SBOM;
- `notice_sha256`: the exact SHA-256 file hash of that notice in the SBOM.

These are human assertions, not evidence that MultiCodex has performed legal
analysis. Review the full relevant notices, exceptions and redistribution terms;
do not populate dispositions automatically. No filled approval is supplied by
the repository. The gate rejects duplicates, missing dispositions, unexpected
reviewers, unknown expressions, absent/changed notices and all attempts to waive
version, package or integrity mismatches. Missing retained notices require a
new bundle unless another actually retained notice establishes the applicable
attribution. Changing a bundle or report invalidates its reviewed hashes.

The protected GitHub release environment and human native product acceptance
remain mandatory. An inventory with open blockers is **not release-ready**.

## Installed storage smoke and update contract

After `npm ci --omit=dev --ignore-scripts`, the builder runs
`bridge/smoke_installed.mjs` first with the pinned source runtime and again with
the bundled `node.exe` and actual `runtime/node_modules` tree. It imports the real
`codex-multi-auth@2.26.0` package/export, checks `getStoragePath`, exercises health
and read-only inventory against an isolated synthetic account, verifies
credential redaction and compares all fixture file hashes before/after. It uses
temporary home/storage overrides and never calls upstream CLI, migration,
postinstall, real OAuth or an existing account store. Results identify their
Node version explicitly. These are compatibility probes, not account acceptance.

The supported release combination remains Python 3.12.10 x64 / PyInstaller
6.20.0 / Node 22.23.5 / codex-multi-auth 2.26.0 / Inno Setup 6.7.1 or 6.7.3.
Older Node 22.19.0 evidence does not accept the current runtime. An upstream
update requires a separately reviewed lock/integrity change, storage-schema and
redaction tests, this installed-package smoke with the pinned/bundled Node,
updated SBOM/notice review and the full native acceptance. Never enable foreign
installation scripts to make an update pass.

Format reference: [CycloneDX 1.6 JSON](https://cyclonedx.org/docs/1.6/json/).
