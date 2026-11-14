param(
    [string]$InnoCompiler
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    if (![Environment]::Is64BitOperatingSystem -or $env:OS -ne 'Windows_NT') { throw 'Windows x64 is required' }
    New-Item -ItemType Directory -Force evidence,output,build/downloads | Out-Null
    if (!$InnoCompiler) {
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (!$InnoCompiler -or !(Test-Path -LiteralPath $InnoCompiler)) {
        throw 'Install Inno Setup 6 first: winget install --id JRSoftware.InnoSetup --exact --version 6.7.3'
    }

    if (!(Test-Path .venv/Scripts/python.exe)) {
        & python -c 'import sys; assert sys.version_info[:3] == (3, 12, 10) and sys.maxsize > 2**32'
        if ($LASTEXITCODE -eq 0) {
            & python -m venv .venv
        } else {
            & py -3.12 -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Install CPython 3.12.10 x64 first' }
    }
    $python = Join-Path $root '.venv/Scripts/python.exe'
    & $python -c 'import sys; assert sys.version_info[:3] == (3, 12, 10) and sys.maxsize > 2**32, "Build requires CPython 3.12.10 x64"'
    if ($LASTEXITCODE -ne 0) { throw 'Use a CPython 3.12.10 x64 virtual environment' }
    & $python -m pip install --only-binary=:all: --require-hashes -r requirements-build.windows-x64.lock
    if ($LASTEXITCODE -ne 0) { throw 'Locked Python installation failed' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are inconsistent' }

    # This official archive supplies both the runtime and its full license.
    $archive = Join-Path $root 'build/downloads/node-v22.19.0-win-x64.zip'
    $nodeHash = 'ea3fad0e67a991d8477d8c01344b56e69c676ccb733f065b22436994b1253f86'
    if (!(Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest 'https://nodejs.org/dist/v22.19.0/node-v22.19.0-win-x64.zip' -OutFile $archive
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower() -ne $nodeHash) { throw 'Node archive checksum mismatch' }
    Expand-Archive -LiteralPath $archive -DestinationPath build/downloads -Force
    $nodeRoot = Join-Path $root 'build/downloads/node-v22.19.0-win-x64'
    $node = Join-Path $nodeRoot 'node.exe'
    $oldPath = $env:PATH
    $env:PATH = "$nodeRoot;$oldPath"
    try {
        & (Join-Path $nodeRoot 'npm.cmd') ci --prefix bridge --omit=dev --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Locked Node installation failed' }
        & $python -m unittest discover -s tests -v *> evidence/python-tests.txt
        if ($LASTEXITCODE -ne 0) { Get-Content evidence/python-tests.txt; throw 'Python tests failed' }
        & $node --test bridge/tests/service.test.mjs *> evidence/node-tests.txt
        if ($LASTEXITCODE -ne 0) { Get-Content evidence/node-tests.txt; throw 'Node tests failed' }
        & $python -m compileall -q multicodex tools run.py
        if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed' }
        & $node --check bridge/service.mjs
        if ($LASTEXITCODE -ne 0) { throw 'Node syntax check failed' }
        & $python run.py --self-check --report evidence/source-runtime.json
        if ($LASTEXITCODE -ne 0) { throw 'Source runtime check failed' }
        & $python run.py --gui-smoke --report evidence/source-gui.json
        if ($LASTEXITCODE -ne 0) { throw 'Source GUI check failed' }
        & $python -m PyInstaller packaging/MultiCodex.spec --noconfirm --clean *> evidence/pyinstaller.txt
        if ($LASTEXITCODE -ne 0) { Get-Content evidence/pyinstaller.txt; throw 'PyInstaller failed' }
    } finally {
        $env:PATH = $oldPath
    }

    $bundle = Join-Path $root 'dist/MultiCodex'
    $runtime = Join-Path $bundle 'runtime'
    New-Item -ItemType Directory -Force $runtime | Out-Null
    Copy-Item -LiteralPath $node -Destination (Join-Path $runtime 'node.exe')
    Copy-Item -LiteralPath (Join-Path $nodeRoot 'LICENSE') -Destination (Join-Path $runtime 'Node-LICENSE.txt')
    Copy-Item bridge/service.mjs $runtime
    Copy-Item bridge/node_modules $runtime -Recurse
    Copy-Item LICENSE,THIRD_PARTY_NOTICES.md,README.md $bundle
    Copy-Item licenses $bundle -Recurse
    if (!(Test-Path "$runtime/node_modules/codex-multi-auth/package.json")) { throw 'Upstream package missing from bundle' }
    Copy-Item bridge/package-lock.json evidence/resolved-node-lock.json -Force
    Copy-Item requirements-build.windows-x64.lock evidence/resolved-python-lock.txt -Force
    & $python -m pip freeze | Set-Content evidence/resolved-python-packages.txt

    foreach ($mode in @('self-check','gui-smoke')) {
        $name = if ($mode -eq 'self-check') { 'runtime' } else { 'gui' }
        $report = Join-Path $root "evidence/packaged-$name.json"
        if (Test-Path -LiteralPath $report) { Remove-Item -LiteralPath $report }
        $app = Join-Path $bundle 'MultiCodex.exe'
        $process = Start-Process -FilePath $app -ArgumentList "--$mode --report `"$report`"" -WindowStyle Hidden -PassThru
        if (!$process.WaitForExit(60000)) { $process.Kill($true); throw "Packaged $name check timed out" }
        $process.Refresh()
        if ($process.ExitCode -ne 0 -or !(Get-Content -Raw $report | ConvertFrom-Json).ready) { throw "Packaged $name check failed" }
    }

    $version = (& $python -c 'from multicodex import __version__; print(__version__)').Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$') { throw 'Invalid build version' }
    if ($env:GITHUB_REF_TYPE -eq 'tag' -and $env:GITHUB_REF_NAME -ne "v$version") { throw 'Tag and source version differ' }
    & $InnoCompiler "/DAppVersion=$version" packaging/MultiCodex.iss *> evidence/inno-compile.txt
    if ($LASTEXITCODE -ne 0) { Get-Content evidence/inno-compile.txt; throw 'Inno Setup failed' }
    $setup = Join-Path $root "output/Codex-Multi-Studio-Setup-v$version.exe"
    if (!(Test-Path $setup) -or (Get-Item $setup).Length -lt 100kb) { throw 'Installer missing or too small' }
    & "$PSScriptRoot/installer_smoke.ps1" -Installer $setup -ReportDirectory evidence/installed

    $commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify source commit' }
    $status = @(& git status --porcelain --untracked-files=all)
    $commit | Set-Content evidence/source-commit.txt
    & git diff --binary HEAD | Set-Content -Encoding utf8 evidence/source-changes.patch
    & git ls-files --others --exclude-standard | Set-Content evidence/untracked-source-files.txt
    $fileHashes = @{}
    $sourceFiles = @(& git ls-files --cached --others --exclude-standard)
    foreach ($file in $sourceFiles) {
        if (Test-Path -LiteralPath $file -PathType Leaf) { $fileHashes[$file] = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower() }
    }
    $fileHashes | ConvertTo-Json -Depth 3 | Set-Content evidence/source-sha256.json
    @{
        built_at = [DateTimeOffset]::Now.ToString('o')
        source_commit = $commit
        source_dirty = ($status.Count -gt 0)
        windows = [Environment]::OSVersion.VersionString
        python = (& $python --version | Out-String).Trim()
        node = (& $node --version | Out-String).Trim()
        node_archive_sha256 = $nodeHash
        compiler = (Resolve-Path $InnoCompiler).Path
        compiler_sha256 = (Get-FileHash -LiteralPath $InnoCompiler -Algorithm SHA256).Hash.ToLower()
        setup_sha256 = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLower()
        scope = 'local development build; native OAuth/multi-instance acceptance is still required for release'
    } | ConvertTo-Json | Set-Content evidence/build.json
    Compress-Archive -Path $bundle -DestinationPath "output/MultiCodex-$version-win-x64-portable.zip" -Force
    Compress-Archive -Path evidence/* -DestinationPath output/build-evidence.zip -Force
    Get-ChildItem output -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | ForEach-Object {
        "$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower())  $($_.Name)"
    } | Set-Content output/SHA256SUMS.txt
    Write-Host "Verified installer: $setup"
} finally {
    Pop-Location
}
