param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$ReportDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($env:TEMP) -or [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw 'TEMP and LOCALAPPDATA must be set for installer verification'
}
if (!(Test-Path -LiteralPath $Installer -PathType Leaf)) { throw 'Installer path must reference a file' }
$Installer = (Resolve-Path -LiteralPath $Installer).Path
New-Item -ItemType Directory -Force $ReportDirectory | Out-Null
$ReportDirectory = (Resolve-Path $ReportDirectory).Path
# A probe must never replace the registration of a real user installation.
$uninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{CCB8A29E-9E8D-4856-976E-0C873B4C98A2}_is1'
if (Test-Path -LiteralPath $uninstallKey) { throw 'MultiCodex is already installed; run installer verification in a clean Windows account' }
$probeId = [guid]::NewGuid().ToString('N')
$destination = Join-Path $env:TEMP "MultiCodex Install Probe $probeId"
$stateRoot = Join-Path $env:LOCALAPPDATA 'MultiCodex'
$sentinel = Join-Path $stateRoot "installer-preserve-$probeId.txt"
if (Test-Path -LiteralPath $destination) { throw 'Refusing to reuse a test installation directory' }
New-Item -ItemType Directory -Force $stateRoot | Out-Null
'Synthetic preservation probe; no credentials' | Set-Content -LiteralPath $sentinel
$originalHash = (Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash
function Invoke-Checked([string]$File, [string]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (!$process.WaitForExit(120000)) {
        # Only this newly started test process, not any process matched by name.
        $process.Kill($true)
        throw 'Owned installer verification process exceeded its deadline'
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Verification process returned $($process.ExitCode)" }
}
try {
    $installLog = Join-Path $ReportDirectory 'install.log'
    Invoke-Checked $Installer "/SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=`"$destination`" /LOG=`"$installLog`""
    $app = Join-Path $destination 'MultiCodex.exe'
    if (!(Test-Path $app)) { throw 'Installed executable missing' }
    $runtimeReport = Join-Path $ReportDirectory 'installed-runtime.json'
    Invoke-Checked $app "--self-check --report `"$runtimeReport`""
    $guiReport = Join-Path $ReportDirectory 'installed-gui.json'
    $screenshots = Join-Path $ReportDirectory 'screenshots'
    Invoke-Checked $app "--gui-smoke --report `"$guiReport`" --screenshot-dir `"$screenshots`""
    if (!(Get-Content -Raw $runtimeReport | ConvertFrom-Json).ready) { throw 'Installed runtime not ready' }
    if (!(Get-Content -Raw $guiReport | ConvertFrom-Json).ready) { throw 'Installed GUI not ready' }
    # Exercise an upgrade over the same installation before uninstalling it.
    Invoke-Checked $Installer "/SP- /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /DIR=`"$destination`""
    if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $originalHash) { throw 'Upgrade changed external user data' }
    $uninstaller = Join-Path $destination 'unins000.exe'
    if (!(Test-Path $uninstaller)) { throw 'Uninstaller missing' }
    Invoke-Checked $uninstaller '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART'
    if (Test-Path $app) { throw 'Application executable remains after uninstall' }
    if ((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash -ne $originalHash) { throw 'Uninstall changed external user data' }
    @{
        ready = $true
        scope = 'install, runtime, real GUI, same-version upgrade and uninstall; no real OAuth'
        setup_sha256 = (Get-FileHash $Installer -Algorithm SHA256).Hash.ToLower()
    } | ConvertTo-Json | Set-Content (Join-Path $ReportDirectory 'installer-smoke.json')
} finally {
    # Remove only the exact test file created above, never the user-data directory.
    if (Test-Path $sentinel) { Remove-Item -LiteralPath $sentinel }
}
