# MultiCodex — development source (0.2.0-dev)

> **Development build, not a finished Windows release.** No installer or GitHub Release is available yet.

The complete, locally tested source tree (67 files) is preserved in [`MultiCodex-source-0.2.0-dev.tar.xz`](MultiCodex-source-0.2.0-dev.tar.xz). It is a compressed Git export, **not an executable**. The import workflow under `.github/workflows/import-source.yml` is intended to unpack that same source tree into normal files, but its initial GitHub Actions run failed before a runner started. Until it runs successfully, use the archive directly.

**To extract:**

```bash
mkdir MultiCodex-source
cd MultiCodex-source
tar -xJf ../MultiCodex-source-0.2.0-dev.tar.xz
```

**Source SHA-256:** `6dfdb9db6c5650d839e8f9848e01ab9a86e55e416814395a241888d2484ae6e8`  
**Git tree after extraction:** `ad822d40c7caecdda276b3a99fbc81a09ccc8d09`  
**Local development commit (not a remote commit):** `893e3e29589ba69f2de80d109fef8e62885bc078`.

Local verification completed: 107 Python unit tests and 9 Node tests passed. Native Windows installer, desktop OAuth and end-to-end validation remain outstanding. No accounts, tokens, session files or browser profiles are included.
