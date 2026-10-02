param(
    [Parameter(Mandatory = $true)][string]$FrameHost,
    [Parameter(Mandatory = $true)][string]$PcAddress,
    [int]$Port = 9000,
    [int]$Hz = 90,
    [switch]$Demo
)
$ErrorActionPreference = 'Stop'
if ($FrameHost -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*$') { throw 'Use a Frame IP address or hostname.' }
$parsedAddress = $null
if (-not [System.Net.IPAddress]::TryParse($PcAddress, [ref]$parsedAddress) -or $parsedAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) { throw 'PcAddress must be an IPv4 address.' }
$PcAddress = $parsedAddress.ToString()
if ($Port -lt 1 -or $Port -gt 65535 -or $Hz -lt 1 -or $Hz -gt 1000) { throw 'Invalid port or rate.' }
$sshExe = Join-Path $env:WINDIR 'System32\OpenSSH\ssh.exe'
$scpExe = Join-Path $env:WINDIR 'System32\OpenSSH\scp.exe'
$tarExe = Join-Path $env:WINDIR 'System32\tar.exe'
foreach ($toolPath in @($sshExe, $scpExe, $tarExe)) { if (-not (Test-Path -LiteralPath $toolPath)) { throw "Missing tool: $toolPath" } }
$projectRoot = Split-Path -Parent $PSScriptRoot
$artifactsPath = Join-Path $projectRoot 'artifacts'
New-Item -ItemType Directory -Path $artifactsPath -Force | Out-Null
$packagePath = Join-Path $artifactsPath 'frame-pose-sender.tar'
& $tarExe -cf $packagePath -C $projectRoot non_pc_streaming/__init__.py non_pc_streaming/frame_sender.py non_pc_streaming/vendor general/__init__.py general/pose_wire.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
$remoteTarget = "steamos@$FrameHost"
Write-Host 'Authenticate with your headset password if prompted. The password is not saved.'
& $sshExe $remoteTarget 'mkdir -p ~/frame_pose_sender'
if ($LASTEXITCODE -ne 0) { throw 'SSH connection failed. Enable Developer Mode and set the user password on Frame.' }
& $scpExe $packagePath "${remoteTarget}:frame_pose_sender/sender.tar"
if ($LASTEXITCODE -ne 0) { throw 'Upload failed.' }
& $sshExe $remoteTarget 'cd ~/frame_pose_sender && tar -xf sender.tar && python3 --version && uname -m'
if ($LASTEXITCODE -ne 0) { throw 'Extraction or Python availability check failed.' }
$demoOption = if ($Demo) { ' --demo' } else { '' }
Write-Host 'Starting the sender. Keep this terminal open; Ctrl+C stops it.'
& $sshExe -t $remoteTarget "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc $PcAddress --port $Port --hz $Hz$demoOption"
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 130) { throw 'Sender exited with an error. Check the message above.' }
