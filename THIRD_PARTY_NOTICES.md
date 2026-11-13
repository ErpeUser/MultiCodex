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
- darkdetect and Pillow are transitive GUI dependencies; retain their installed distribution metadata/notices.
- Node 22.19.0 is selected by the build workflow; its LICENSE must be present before packaging.
- PyInstaller 6.20.0 is the build dependency; retain applicable license/exception notices.
- Inno Setup is an external build compiler, not redistributed by MultiCodex; record the actual compiler version and review its terms before release.

Dependency metadata is collected into the packaged application. This repository contains no copied system font files. A complete transitive lockfile and final distribution-license audit remain release prerequisites.
