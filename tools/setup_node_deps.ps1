# Install pinned Node packages physically under generated/runtime.
# The bridge/node_modules directory is only a local Windows junction for ESM lookup.
param([string]$NpmCommand = 'npm.cmd')
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
$bridge = Join-Path $root 'bridge'
$prefix = Join-Path $root 'generated/runtime/dependencies/node'
$cache = Join-Path $root 'generated/runtime/cache/npm'
$link = Join-Path $bridge 'node_modules'
$actual = Join-Path $prefix 'node_modules'
New-Item -ItemType Directory -Path $prefix,$cache -Force | Out-Null

if (Test-Path -LiteralPath $link) {
    $item = Get-Item -LiteralPath $link -Force
    if (-not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
        throw 'Refusing to overwrite a physical bridge/node_modules directory'
    }
    $target = @($item.Target)[0]
    if (-not $target -or ([System.IO.Path]::GetFullPath($target)).TrimEnd('\') -ne
        ([System.IO.Path]::GetFullPath($actual)).TrimEnd('\')) {
        throw 'Refusing an unexpected bridge/node_modules junction target'
    }
}
Copy-Item -LiteralPath (Join-Path $bridge 'package.json') -Destination (Join-Path $prefix 'package.json') -Force
Copy-Item -LiteralPath (Join-Path $bridge 'package-lock.json') -Destination (Join-Path $prefix 'package-lock.json') -Force
$env:npm_config_cache = $cache
& $NpmCommand ci --prefix $prefix --omit=dev --ignore-scripts --no-audit --no-fund
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath (Join-Path $actual 'codex-multi-auth/package.json'))) {
    throw 'Pinned Node package installation failed'
}
if (!(Test-Path -LiteralPath $link)) {
    New-Item -ItemType Junction -Path $link -Target $actual | Out-Null
}
Write-Host "Node packages centralized at $actual"
