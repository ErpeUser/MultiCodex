param(
    [string]$FigmaPluginId
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $before = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the current commit before pull' }
    & py -3.12 tools/github_sync.py
    if ($LASTEXITCODE -ne 0) { throw 'GitHub branch or pull-request review failed' }
    & git pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) { throw 'Fast-forward pull from origin/main failed' }
    $after = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the pulled commit' }
    if ($before -eq $after) {
        Write-Output 'POST_PULL_NO_SOURCE_CHANGE'
        exit 0
    }
    $arguments = @('tools/post_pull.py', '--from', $before, '--to', $after, '--run')
    if ($FigmaPluginId) { $arguments += @('--figma-plugin-id', $FigmaPluginId) }
    & py -3.12 @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Affected artifact regeneration or smoke execution failed' }
} finally {
    Pop-Location
}
