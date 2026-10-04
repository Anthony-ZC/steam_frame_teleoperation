# Frame local pose sender prototype

This prototype runs a Python/OpenVR background client **on Frame**, and sends
only controller transforms to a Windows UDP receiver. It submits no video and
does not connect to PC SteamVR. It requires Frame's own local SteamVR runtime to
be running and tracking. That runtime access has not yet been tested on Frame.
This is a prototype, not a confirmed replacement for streaming yet.

## Headset setup

1. Enable Steam Settings > System > Enable Developer Mode.
2. Under Developer, set the user password; keep it private.
3. Connect Frame and the PC to the same Wi-Fi/LAN. Use the headset's Wi-Fi IP
   address and the PC's LAN IPv4 address. Pairing to the streaming dongle alone
   does not guarantee an ordinary IP route usable by this prototype.
4. Keep Frame awake in its **local** VR dashboard, with controllers in view of
   the tracking cameras. The wear sensor still needs to detect the headset as
   worn. This sender does not override sleep or tracking policies.

Valve documents local Linux ARM64/OpenVR apps and Developer Mode:
https://partner.steamgames.com/doc/steamhardware/steamframe/engines/custom
https://partner.steamgames.com/doc/steamhardware/steamframe/setup
https://partner.steamgames.com/doc/steamhardware/steamframe/debugging

## PC receiver

From the repository root, using its virtual environment:

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses --udp --sender-ip FRAME_WIFI_IP
```

Replace `FRAME_WIFI_IP` with Frame's actual IPv4 address. The default listening
port is UDP 9000, and stale poses disappear after 250 ms. `--bind PC_LAN_IP`
limits listening to that interface. `--port` and `--timeout` are configurable.
If Windows Firewall blocks traffic, allow inbound UDP 9000 from the Frame IP
on the appropriate network profile. Do not turn the firewall off. No firewall
settings are changed by the project.

## Upload and run on Frame

Open PowerShell at the repository root:

```powershell
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_WIFI_IP -PcAddress PC_LAN_IP
```

This creates `artifacts/frame-pose-sender.tar`, packs the sender, `config.toml`
and the shared protocol/OpenVR sampler with their package folders, uploads it with SCP to `~/frame_pose_sender`, checks
Python availability, then runs it through SSH. The documented default user is
`steamos`. Verify the SSH host fingerprint using a trusted connection before
accepting a new host. Enter the headset password directly in your terminal.
The script does not save credentials. Keep the SSH terminal open. Ctrl+C stops
the sender. No root access, OS packages, background service, or read-only OS
changes are required by this package.

You can first add `-Demo` to send synthetic poses **from Frame**. That validates
Wi-Fi and the receiver independently of local OpenVR. Then run without `-Demo`
to test live tracking. The sender polls at 90 Hz by default; use `-Hz 120` to
request 120 Hz. This is a polling rate, not a verified sensor update rate.

Alternatively, upload and extract `artifacts/frame-pose-sender.tar` using WinSCP.
Preserve its `non_pc_streaming/` and `general/` folder structure. From the
directory containing those folders, run:

```sh
cd ~/frame_pose_sender
python3 -m non_pc_streaming.frame_sender --pc PC_LAN_IP --hz 90
```

## Coordinates and packets

The packet contains row-major 3x4 **device-origin** transforms in Frame's local
SteamVR standing space: meters, +X right, +Y up, -Z forward. The Windows viewer
remaps display axes only. Frame's local origin may differ from the previous PC
streaming origin. Recenter/calibrate again before reusing a coordinate mapping.

Each UDP snapshot contains the fully tracked controllers (tracking result 200).
Missing devices disappear immediately when a new snapshot arrives. An empty
snapshot clears the viewer. Loss of packets hides poses after the timeout.
Sequence numbers reject duplicate/reordered packets. A random session ID allows
sender restarts after the previous stream times out. This prototype accepts one
sender at a time; `--sender-ip` narrows acceptance to the requested headset.
UDP is unauthenticated; use it on a trusted LAN.

Each packet is 32 bytes plus 56 bytes per controller. Two controllers at 90 Hz
send about 13 kB/s of UDP payload, versus a video stream. Sender monotonic time
is diagnostic only; its clock is not synchronized with the PC. PC receipt time
does not prove the hardware sample is fresh when a runtime repeats a pose.

## Verification and limits

Run `python -B -m unittest discover -s general/tests -v` from the repository root with the
existing Windows virtual environment. These tests cover real loopback UDP,
matrix ordering, malformed packets, nonfinite values, duplicates, reordering,
restarts, lost tracking, timeouts, and the standalone synthetic sender process.

The bundled ARM64 OpenVR library and unmodified pyopenvr bindings have licenses
and provenance under `vendor`. The headset needs Python 3.11+ (Frame ships 3.12) and a compatible
local SteamVR runtime. The ARM64 library cannot be loaded on this Windows PC.
Local OpenVR permissions, pairing, pose updates, and tracking without a PC video
stream require on-headset verification. If Python or local background OpenVR
is unavailable, the next approach is a native ARM64 or Android OpenXR app.
