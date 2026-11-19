param(
    [string]$InnoCompiler
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $initialCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify source commit before build' }
    $initialStatus = @(& git status --porcelain --untracked-files=all)
    if ($initialStatus.Count -gt 0) { throw 'Build requires a clean source tree' }
    if (![Environment]::Is64BitOperatingSystem -or $env:OS -ne 'Windows_NT') { throw 'Windows x64 is required' }
    New-Item -ItemType Directory -Force generated/runtime/evidence,generated/runtime/output,generated/runtime/downloads,generated/runtime/dependencies/python,generated/runtime/dependencies/toolchains | Out-Null
    $env:PYTHONPYCACHEPREFIX = Join-Path $root 'generated/runtime/cache/pycache'
    $env:PIP_CACHE_DIR = Join-Path $root 'generated/runtime/cache/pip'
    $env:npm_config_cache = Join-Path $root 'generated/runtime/cache/npm'
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $root 'generated/runtime/cache/pyinstaller'
    $env:RUFF_CACHE_DIR = Join-Path $root 'generated/runtime/cache/ruff'
    if (@(Get-ChildItem generated/runtime/evidence -Force -ErrorAction SilentlyContinue).Count -gt 0 -or
        @(Get-ChildItem generated/runtime/output -Force -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'Evidence and output directories must be empty before a reproducible build'
    }
    if (!$InnoCompiler) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (!$InnoCompiler -or !(Test-Path -LiteralPath $InnoCompiler)) {
        throw 'Install a verified Inno Setup 6.7.1 or 6.7.3 compiler before building'
    }
    if (!(Test-Path generated/runtime/dependencies/python/venv/Scripts/python.exe)) {
        & python -c 'import sys; assert sys.version_info[:3] == (3, 12, 10) and sys.maxsize > 2**32'
        if ($LASTEXITCODE -eq 0) {
            & python -m venv generated/runtime/dependencies/python/venv
        } else {
            & py -3.12 -m venv generated/runtime/dependencies/python/venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Install CPython 3.12.10 x64 first' }
    }
    $python = Join-Path $root 'generated/runtime/dependencies/python/venv/Scripts/python.exe'
    & $python -c 'import sys; assert sys.version_info[:3] == (3, 12, 10) and sys.maxsize > 2**32, "Build requires CPython 3.12.10 x64"'
    if ($LASTEXITCODE -ne 0) { throw 'Use a CPython 3.12.10 x64 virtual environment' }
    $innoVersion = (& $python tools/compiler_identity.py $InnoCompiler | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup compiler identity could not be verified' }
    if ($innoVersion -notin @('6.7.1','6.7.3')) { throw "Unsupported Inno Setup version: $innoVersion" }
    & $python -m pip install --only-binary=:all: --require-hashes -r generated/project/config/python/requirements-build.windows-x64.lock
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python installation failed' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are inconsistent' }
    & $python tools/check_references.py
    if ($LASTEXITCODE -ne 0) { throw 'Project documentation references are invalid' }

    # This official archive supplies both the runtime and its full license.
    $archive = Join-Path $root 'generated/runtime/downloads/node-v22.23.5-win-x64.zip'
    $nodeRoot = Join-Path $root 'generated/runtime/dependencies/toolchains/node-v22.23.5-win-x64'
    $nodeHash = '4a191082e9706866830379d577d2cc8a50c776fcd9436a8d061b063ed0d9a0e3'
    if (!(Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest 'https://nodejs.org/dist/v22.23.5/node-v22.23.5-win-x64.zip' -OutFile $archive -TimeoutSec 120
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $nodeHash) { throw 'Node archive checksum mismatch' }
    if (Test-Path -LiteralPath $nodeRoot) { Remove-Item -LiteralPath $nodeRoot -Recurse -Force }
    Expand-Archive -LiteralPath $archive -DestinationPath generated/runtime/dependencies/toolchains -Force
    $node = Join-Path $nodeRoot 'node.exe'
    $oldPath = $env:PATH
    $env:PATH = "$nodeRoot;$oldPath"
    try {
        & "$PSScriptRoot/setup_node_deps.ps1" -NpmCommand (Join-Path $nodeRoot 'npm.cmd')
        if ($LASTEXITCODE -ne 0) { throw 'Locked Node installation failed' }
        & $node bridge/smoke_installed.mjs bridge *> generated/runtime/evidence/source-storage-smoke.json
        if ($LASTEXITCODE -ne 0) { throw 'Installed source storage facade smoke failed' }
        & $python -m unittest discover -s tests -v *> generated/runtime/evidence/python-tests.txt
        if ($LASTEXITCODE -ne 0) { Get-Content generated/runtime/evidence/python-tests.txt; throw 'Python tests failed' }
        & $node --test bridge/tests/service.test.mjs *> generated/runtime/evidence/node-tests.txt
        if ($LASTEXITCODE -ne 0) { Get-Content generated/runtime/evidence/node-tests.txt; throw 'Node tests failed' }
        & $python -m compileall -q multicodex tools run.py
        if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed' }
        & $node --check bridge/service.mjs
        if ($LASTEXITCODE -ne 0) { throw 'Node syntax check failed' }
        & $python run.py --self-check --report generated/runtime/evidence/source-runtime.json
        if ($LASTEXITCODE -ne 0) { throw 'Source runtime check failed' }
        & $python run.py --gui-smoke --report generated/runtime/evidence/source-gui.json
        if ($LASTEXITCODE -ne 0) { throw 'Source GUI check failed' }
        foreach ($dir in @('generated/runtime/dist/MultiCodex','generated/runtime/build/MultiCodex')) {
            $stale = Join-Path $root $dir
            if (Test-Path -LiteralPath $stale) { Remove-Item -LiteralPath $stale -Recurse -Force }
        }
        & $python -m PyInstaller packaging/MultiCodex.spec --distpath generated/runtime/dist --workpath generated/runtime/build/pyinstaller --noconfirm --clean *> generated/runtime/evidence/pyinstaller.txt
        if ($LASTEXITCODE -ne 0) { Get-Content generated/runtime/evidence/pyinstaller.txt; throw 'PyInstaller failed' }
    } finally {
        $env:PATH = $oldPath
    }

    $bundle = Join-Path $root 'generated/runtime/dist/MultiCodex'
    $runtime = Join-Path $bundle 'runtime'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    Copy-Item -LiteralPath $node -Destination (Join-Path $runtime 'node.exe')
    Copy-Item -LiteralPath (Join-Path $nodeRoot 'LICENSE') -Destination (Join-Path $runtime 'Node-LICENSE.txt')
    Copy-Item bridge/service.mjs $runtime
    Copy-Item generated/runtime/dependencies/node/node_modules $runtime -Recurse
    Copy-Item generated/project/licenses/LICENSE,generated/project/licenses/THIRD_PARTY_NOTICES.md,generated/project/docs/README.md $bundle
    Copy-Item -LiteralPath generated/project/licenses/third-party -Destination (Join-Path $bundle 'licenses') -Recurse
    if (!(Test-Path "$runtime/node_modules/codex-multi-auth/package.json")) { throw 'Upstream package missing from bundle' }
    Copy-Item bridge/package-lock.json generated/runtime/evidence/resolved-node-lock.json -Force
    Copy-Item generated/project/config/python/requirements-build.windows-x64.lock generated/runtime/evidence/resolved-python-lock.txt -Force
    & $python -m pip freeze | Set-Content generated/runtime/evidence/resolved-python-packages.txt
    & $node bridge/smoke_installed.mjs $runtime *> generated/runtime/evidence/bundled-storage-smoke.json
    if ($LASTEXITCODE -ne 0) { throw 'Bundled storage facade smoke failed' }

    foreach ($mode in @('self-check','gui-smoke')) {
        $name = if ($mode -eq 'self-check') { 'runtime' } else { 'gui' }
        $report = Join-Path $root "generated/runtime/evidence/packaged-$name.json"
        if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report }
        $app = Join-Path $bundle 'MultiCodex.exe'
        $process = Start-Process -FilePath $app -ArgumentList "--$mode --report `"$report`"" -WindowStyle Hidden -PassThru
        if (!$process.WaitForExit(60000)) { $process.Kill($true); throw "Packaged $name check timed out" }
        $process.Refresh()
        if ($process.ExitCode -ne 0 -or !(Get-Content -Raw $report | ConvertFrom-Json).ready) { throw "Packaged $name check failed" }
    }

    $bundledNodeVersion = (& $node --version | Out-String).Trim().TrimStart('v')
    if ($LASTEXITCODE -ne 0 -or $bundledNodeVersion -ne '22.23.5') { throw 'Bundled Node version differs from pinned toolchain' }
    & $python tools/supply_chain.py --bundle $bundle --python-lock generated/project/config/python/requirements-build.windows-x64.lock --node-lock bridge/package-lock.json --commit $initialCommit --node-version $bundledNodeVersion --node-archive-sha256 $nodeHash *> generated/runtime/evidence/supply-chain-summary.json
    if ($LASTEXITCODE -ne 0) { throw 'Post-build SBOM inventory failed' }
    foreach ($name in @('SBOM.cdx.json','license-report.json')) {
        Copy-Item -LiteralPath (Join-Path $bundle $name) -Destination (Join-Path $root "generated/runtime/evidence/$name")
        Copy-Item -LiteralPath (Join-Path $bundle $name) -Destination (Join-Path $root "generated/runtime/output/$name")
    }
    $licenseReport = Get-Content -Raw (Join-Path $bundle 'license-report.json') | ConvertFrom-Json
    if (!$licenseReport.ready) { Write-Warning 'Development bundle built with explicit license-review blockers; publication remains blocked.' }

    $version = (& $python -c 'from multicodex import __version__; print(__version__)').Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$') { throw 'Invalid build version' }
    if ($env:GITHUB_REF_TYPE -eq 'tag' -and $env:GITHUB_REF_NAME -ne "v$version") { throw 'Tag and source version differ' }
    & $InnoCompiler "/DAppVersion=$version" packaging/MultiCodex.iss *> generated/runtime/evidence/inno-compile.txt
    if ($LASTEXITCODE -ne 0) { Get-Content generated/runtime/evidence/inno-compile.txt; throw 'Inno Setup failed' }
    $setup = Join-Path $root "generated/runtime/output/Codex-Multi-Studio-Setup-v$version.exe"
    if (!(Test-Path $setup) -or (Get-Item $setup).Length -lt 100kb) { throw 'Installer missing or too small' }
    & "$PSScriptRoot/installer_smoke.ps1" -Installer $setup -ReportDirectory generated/runtime/evidence/installed

    $commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify source commit' }
    $finalCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $finalCommit -ne $initialCommit) { throw 'Source commit changed during build' }
    $status = @(& git status --porcelain --untracked-files=all)
    if ($status | Where-Object { $_ -notmatch '^(\?\?|!!)' }) { throw 'Tracked source changed during build' }
    $commit | Set-Content generated/runtime/evidence/source-commit.txt
    & git diff --binary HEAD | Set-Content -Encoding utf8 generated/runtime/evidence/source-changes.patch
    & git ls-files --others --exclude-standard | Set-Content generated/runtime/evidence/untracked-source-files.txt
    $fileHashes = @{}
    $sourceFiles = @(& git ls-files --cached --others --exclude-standard)
    foreach ($file in $sourceFiles) {
        if (Test-Path -LiteralPath $file -PathType Leaf) { $fileHashes[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower() }
    }
    $fileHashes | ConvertTo-Json -Depth 3 | Set-Content generated/runtime/evidence/source-sha256.json
    @{
        built_at = [DateTimeOffset]::Now.ToString('o')
        source_commit = $commit
        initial_commit = $initialCommit
        final_commit = $finalCommit
        source_dirty = ($status.Count -gt 0)
        windows = [Environment]::OSVersion.VersionString
        python = (& $python --version | Out-String).Trim()
        pip = (& $python -m pip --version | Out-String).Trim()
        node = (& $node --version | Out-String).Trim()
        npm = (& (Join-Path $nodeRoot 'npm.cmd') --version | Out-String).Trim()
        git = (& git --version | Out-String).Trim()
        node_archive_sha256 = $nodeHash
        compiler = (Resolve-Path $InnoCompiler).Path
        inno_version = $innoVersion
        compiler_sha256 = (Get-FileHash -LiteralPath $InnoCompiler -Algorithm SHA256).Hash.ToLower()
        setup_sha256 = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLower()
        sbom_sha256 = (Get-FileHash -LiteralPath (Join-Path $bundle 'SBOM.cdx.json') -Algorithm SHA256).Hash.ToLower()
        license_report_sha256 = (Get-FileHash -LiteralPath (Join-Path $bundle 'license-report.json') -Algorithm SHA256).Hash.ToLower()
        licenses_ready = $licenseReport.ready
        scope = 'local development build; native OAuth/multi-instance acceptance is still required for release'
    } | ConvertTo-Json | Set-Content generated/runtime/evidence/build.json
    Compress-Archive -Path $bundle -DestinationPath "generated/runtime/output/MultiCodex-$version-win-x64-portable.zip" -Force
    Compress-Archive -Path generated/runtime/evidence/* -DestinationPath generated/runtime/output/build-evidence.zip -Force
    Get-ChildItem generated/runtime/output -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | ForEach-Object {
        "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
    } | Set-Content generated/runtime/output/SHA256SUMS.txt
    Write-Host "Verified installer: $setup"
} finally {
    Pop-Location
}
