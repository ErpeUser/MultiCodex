# Run from a clean Windows 11 x64 test account, not a production account.
#Requires -Version 7.0
param(
    [ValidateSet(100,125,150,200)][int]$Dpi = 100,
    [switch]$CaptureOnly,
    [string]$InnoCompiler
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Split-Path $PSScriptRoot -Parent

function Assert-PlainPath([string]$Path) {
    $current = [System.IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                throw 'Linked/junction paths are not accepted for native evidence'
            }
        }
        $parent = [System.IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
}

Push-Location $root
try {
    if ($env:OS -ne 'Windows_NT' -or ![Environment]::Is64BitOperatingSystem) {
        throw 'Windows x64 is required; no native result can be produced here'
    }
    Assert-PlainPath $root
    $commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') { throw 'Cannot identify source commit' }
    $dirty = @(& git status --porcelain --untracked-files=all)
    if ($LASTEXITCODE -ne 0 -or $dirty.Count -gt 0) { throw 'Commit all source changes before native verification' }

    if (!$CaptureOnly) {
        # Keep old build evidence intact, outside the source tree. Never delete it.
        $archive = Join-Path ([System.IO.Path]::GetTempPath()) ('MultiCodex-Evidence-' + [guid]::NewGuid().ToString('N'))
        Assert-PlainPath $archive
        New-Item -ItemType Directory -Path $archive | Out-Null
        foreach ($name in @('evidence','output')) {
            $source = Join-Path $root $name
            Assert-PlainPath $source
            if (Test-Path -LiteralPath $source) {
                Move-Item -LiteralPath $source -Destination (Join-Path $archive $name)
            }
        }
        Write-Host "Previous build output preserved: $archive"
        & "$PSScriptRoot/build_windows.ps1" -InnoCompiler $InnoCompiler
        if (!(Test-Path -LiteralPath 'evidence/build.json')) { throw 'Build evidence missing' }
    }
    $python = Join-Path $root '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $python)) { throw 'Run the full build before CaptureOnly' }
    $setups = @(Get-ChildItem -LiteralPath (Join-Path $root 'output') -Filter '*Setup*.exe' -File)
    if ($setups.Count -ne 1) { throw 'Exactly one newly built installer is required' }
    $setup = $setups[0].FullName
    if (!$CaptureOnly) {
        & $python tools/native_evidence.py --evidence evidence --setup $setup --commit $commit --seal-build
        if ($LASTEXITCODE -ne 0) { throw 'Fresh build evidence could not be indexed' }
    }
    if (!(Test-Path -LiteralPath 'evidence/build-index.json')) { throw 'No fresh indexed build; run without CaptureOnly first' }
    $captureRoot = Join-Path $root 'evidence/native-matrix'
    Assert-PlainPath $captureRoot
    $capture = Join-Path $captureRoot "dpi-$Dpi"
    & $python tools/capture_native_matrix.py --output $capture --setup $setup --commit $commit --dpi $Dpi
    if ($LASTEXITCODE -ne 0) { throw 'Native capture failed; partial output is retained, not overwritten' }

    $arguments = @('tools/native_evidence.py','--evidence','evidence','--setup',$setup,'--commit',$commit)
    foreach ($percent in @(100,125,150,200)) {
        $folder = Join-Path $captureRoot "dpi-$percent"
        if (Test-Path -LiteralPath (Join-Path $folder 'manifest.json')) { $arguments += @('--captures',$folder) }
    }
    $run = [guid]::NewGuid().ToString('N')
    $report = Join-Path $root "evidence/native-evidence-$run.json"
    $draft = Join-Path $root "evidence/native-acceptance-$run.DRAFT.json"
    & $python @arguments --output $report --draft $draft
    $result = $LASTEXITCODE
    if ($result -gt 1) { throw 'Evidence validation failed' }
    Write-Host "Machine evidence: $report"
    Write-Host "Unapproved manual-acceptance draft: $draft"
    if ($result -eq 1) { Write-Host 'Matrix incomplete. Change actual Windows display scale, then use -CaptureOnly -Dpi <percent>.' }
    Write-Host 'No release, OAuth result, keyboard validation or multi-instance acceptance is implied.'
    exit $result
} finally {
    Pop-Location
}
