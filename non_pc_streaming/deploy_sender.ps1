param(
    [Parameter(Mandatory = $true)][string]$FrameHost,
    [string]$PcAddress,
    [int]$Port = 9000,
    [int]$Hz = 90,
    [switch]$Demo,
    [switch]$Probe,
    [int]$ProbeSeconds = 20
)
$ErrorActionPreference = 'Stop'
if ($FrameHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') { throw 'Use a Frame IP address or hostname.' }
if ($Probe -and $Demo) { throw '-Probe and -Demo are mutually exclusive.' }
if ($ProbeSeconds -lt 1 -or $ProbeSeconds -gt 600) { throw 'ProbeSeconds must be 1-600.' }
if (-not $Probe) {
    $parsedAddress = $null
    if (-not [System.Net.IPAddress]::TryParse($PcAddress, [ref]$parsedAddress) -or $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'PcAddress must be an IPv4 address.' }
    $PcAddress = $parsedAddress.ToString()
}
# -Hz 0 sends at the unlimited (natural) rate.
if ($Port -lt 1 -or $Port -gt 65535 -or $Hz -lt 0 -or $Hz -gt 1000) { throw 'Invalid port or rate.' }
$sshExe = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scpExe = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$tarExe = Join-Path $env:WINDIR 'System32\tar.exe'
foreach ($toolPath in @($sshExe, $scpExe, $tarExe)) { if (-not (Test-Path -LiteralPath $toolPath)) { throw "Missing tool: $toolPath" } }
$projectRoot = Split-Path -Parent $PSScriptRoot
$artifactsPath = Join-Path $projectRoot 'artifacts'
New-Item -ItemType Directory -Path $artifactsPath -Force | Out-Null
$packagePath = Join-Path $artifactsPath 'frame-pose-sender.tar'
& $tarExe -cf $packagePath --exclude=__pycache__ -C $projectRoot config.toml non_pc_streaming/__init__.py non_pc_streaming/frame_sender.py non_pc_streaming/vendor general/__init__.py general/pose_wire.py general/config.py general/controller_state.py general/demo.py general/openvr_sampler.py general/input diagnostics/__init__.py diagnostics/probe_controller.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
$remoteTarget = "steamos@$FrameHost"
Write-Host 'Authenticate with your headset password if prompted. The password is not saved.'
& $sshExe $remoteTarget 'mkdir -p ~/frame_pose_sender'
if ($LASTEXITCODE -ne 0) { throw 'SSH connection failed. Enable Developer Mode and set the user password on Frame.' }
& $scpExe $packagePath "${remoteTarget}:frame_pose_sender/sender.tar"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
# Remove only this package's own folders so renamed/deleted files do not linger.
# Windows PowerShell drops embedded double quotes when calling ssh.exe; use bash single quotes ('' inside this string).
& $sshExe $remoteTarget 'cd ~/frame_pose_sender && rm -rf general non_pc_streaming diagnostics && tar -xf sender.tar && python3 --version && python3 -c ''import sys; sys.exit(sys.version_info < (3, 11))'' && uname -m'
if ($LASTEXITCODE -ne 0) { throw 'Extraction failed or Python 3.11+ is not available on Frame.' }
if ($Probe) {
    Write-Host "Running the controller probe for $ProbeSeconds s. Touch, press and move every control."
    & $sshExe -t $remoteTarget "cd ~/frame_pose_sender && python3 -m diagnostics.probe_controller --seconds $ProbeSeconds"
    if ($LASTEXITCODE -ne 0) { throw 'Probe failed. Check the Environment section above.' }
    return
}
$demoOption = if ($Demo) { ' --demo' } else { '' }
Write-Host 'Starting the sender. Keep this terminal open; Ctrl+C stops it.'
& $sshExe -t $remoteTarget "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc $PcAddress --port $Port --hz $Hz$demoOption"
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 130) { throw 'Sender exited with an error. Check the message above.' }
