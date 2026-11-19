# Third-party components and provenance

MultiCodex is an independent application. No official ChatGPT or Codex desktop executable is redistributed.

## codex-multi-auth

Repository: https://github.com/ndycode/codex-multi-auth

Pinned direct runtime dependency: **2.26.0**. Copyright (c) 2026 **ndycode**, MIT. The verified license text is retained in `licenses/codex-multi-auth-MIT.txt` (upstream blob `a11f7c081c26453e000e37a4965017405a4c94df`). The runtime package, not a rewritten OAuth stack, supplies the public storage-path facade used for a read-only inventory. No manager CLI `switch`, `status`, repair or first-run setup is invoked. Safe pool-to-managed-session transfer is not implemented.

The Windows workflow copies the installed package and its dependency notices and does not execute npm install scripts. All runtime/transitive notices must be audited before release.

## ai-multi-instance

Repository: https://github.com/Zoltak-Dev/ai-multi-instance

Copyright notice in the actual upstream license is **Copyright (c) 2026 Zoltrak-Dev**; the spelling is retained verbatim in `licenses/ai-multi-instance-MIT.txt` (blob `cc0fd1ccb439ec20e456a17ce10352743acb3bca`). MIT.

The existing profile/environment and MSIX discovery strategy informed the recovered implementation: `CODEX_HOME`, `CODEX_ELECTRON_USER_DATA_PATH`, `CODEX_CLI_PATH` and exact `--user-data-dir` matching. The complete engine is not vendored. Its Claude cookie-decryption and default-profile snapshot code is deliberately not imported. MultiCodex does not claim full upstream test coverage or native compatibility from that reuse.

## Other runtime/build dependencies

- CustomTkinter 5.2.2: MIT.
- psutil 6.1.1: BSD 3-Clause.
- darkdetect 0.8.0 and packaging 26.3 are transitive GUI dependencies; their distribution metadata/notices are bundled.
- Pillow 13.0.0 is an explicit dependency for owned-window GUI screenshots; its distribution metadata/notices are bundled.
- Node 22.23.5 is copied from the official Windows x64 archive with its full LICENSE, after checking the pinned SHA-256.
- PyInstaller 6.20.0 is the build dependency; retain applicable license/exception notices.
- Inno Setup is an external build compiler, not redistributed by MultiCodex; record the actual compiler version and review its terms before release.

Python and PyInstaller notices, installed runtime-distribution metadata, upstream package license files and the repository's `licenses/` directory are retained in the bundle. This repository contains no copied system font files. The verified Python x64 build lock and npm lock cover transitive dependencies; the final distribution-license audit, own app icon and native release acceptance remain prerequisites for publication.

Every new Windows bundle includes `SBOM.cdx.json` and `license-report.json`.
Unknown or missing license attribution remains an explicit publication blocker.
See [the inventory and exact-build review contract](../docs/supply-chain.md).
