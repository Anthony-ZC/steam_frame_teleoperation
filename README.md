# Steam Frame controller toolkit

Read, visualize and log Steam Frame controller data with Python: poses,
velocities, buttons with touch sensing, trigger/grip/thumbstick values,
finger curl and battery. Two ways to get the data to the PC:

| Mode | How | PC needs | Status |
|---|---|---|---|
| **PC streaming** | PC SteamVR, while Frame streams to the PC | SteamVR + an active stream | verified |
| **Standalone** | a small Python sender runs **on Frame** and sends UDP packets | only this repository | verified (2026-10-04) |

The scripts collect and display data only. They do not control a robot.
Tested on Windows 11 and Ubuntu 26.04 (home Wi‑Fi only).

## Setup

64-bit Python 3.11 or newer. Create the virtual environment once:

```powershell
py -3.11 -m venv .venv            # Windows
python3 -m venv .venv             # Ubuntu (needs the python3-venv package)
```

**Activate it in every new terminal**, then install the dependencies once:

```powershell
.\.venv\Scripts\Activate.ps1      # Windows PowerShell (cmd: .venv\Scripts\activate.bat)
source .venv/bin/activate         # Ubuntu / macOS
python -m pip install -r requirements.txt
pip install PyQt6                 # Ubuntu only: GUI backend for the viewer (or: sudo apt install python3-tk)
```

- PowerShell refuses `Activate.ps1`? Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- Run every command from the repository root with `python -m`.
- Frame needs no installation (it uses its own Python 3.12 and the bundled OpenVR library).

## Folder structure

```text
config.toml          Field selection, relative pose mode, OpenVR app type
general/             Shared code: viewer, OpenVR sampler, packet format, config, tests
streaming/           PC streaming mode: SteamVR reader, console/CSV logger
non_pc_streaming/    Standalone mode: Frame sender, UDP receiver, deploy script
diagnostics/         Probes, measurements and benchmark results
artifacts/           Generated previews, packages, measurements (ignored by Git)
```

Each folder's README lists its files and the details:
[general](general/README.md) · [streaming](streaming/README.md) ·
[non_pc_streaming](non_pc_streaming/README.md) · [diagnostics](diagnostics/README.md).

## Minimal files for visualizing

Each row adds to the one above it. `config.toml` is optional (built-in
defaults apply without it).

| Mode | Files | pip packages |
|---|---|---|
| Demo (no hardware) | `general/__init__.py`, `general/visualize_poses.py`, `general/readers.py`, `general/demo.py`, `general/poses.py`, `general/relative_pose.py`, `general/controller_state.py`, `general/config.py` | `numpy`, `matplotlib` |
| + PC streaming | `streaming/__init__.py`, `streaming/frame_pose.py`, `general/openvr_sampler.py`, `general/input/` | + `openvr` |
| + Standalone, PC side | `non_pc_streaming/__init__.py`, `non_pc_streaming/udp_pose.py`, `general/pose_wire.py` | – |
| Standalone, Frame side | `non_pc_streaming/__init__.py`, `non_pc_streaming/frame_sender.py`, `non_pc_streaming/vendor/`, `general/__init__.py`, `general/config.py`, `general/controller_state.py`, `general/demo.py`, `general/pose_wire.py`, `general/openvr_sampler.py`, `general/input/` | none (Frame's Python) |

`general/input/` is only needed when `buttons`, `analog` or `fingers` are
enabled; `general/clock_sync.py` only for `--sync` latency measurements.

## Configuration

`config.toml` (or `--config PATH`) is read by the viewer, the logger and the
Frame sender. `[fields]` turns data groups on or off, `[relative_pose]` sets
the reference mode, `[input]` the OpenVR app type. Details and what each data
group contains: [general/README.md](general/README.md#configuration).

## Viewer

```powershell
python -m general.visualize_poses            # PC streaming
python -m general.visualize_poses --udp --sender-ip FRAME_IP   # standalone
python -m general.visualize_poses --demo     # synthetic, no hardware
```

Hold the controllers still during the 3 s countdown at launch (it captures the
pose reference); **Reset Pose** or `R` recaptures it. Panel legend and
options: [general/README.md](general/README.md#viewer).

**Close the SteamVR dashboard in the headset.** While it is open it receives
all controller input: buttons, analog values and fingers go inactive, only
poses still arrive.

Check what a controller exposes (touch, press and squeeze everything while it runs):

```powershell
python -m diagnostics.probe_controller --seconds 20
```

## PC streaming mode

1. Start SteamVR on the PC and stream from Frame (a minimized desktop is enough).
2. **Close the SteamVR dashboard** in the headset.
3. Keep both controllers awake and in view of the headset's cameras.

```powershell
python -m general.visualize_poses                      # view
python -m streaming.read_poses --csv artifacts/poses.csv   # print + log CSV
```

With the stream off, poses freeze while SteamVR still reports them as
tracked. Details: [streaming/README.md](streaming/README.md).

## Standalone mode

The sender runs on Frame, reads Frame's own VR runtime and sends UDP packets
to the PC. No PC stream and no PC SteamVR are needed.

### 1. Prepare Frame

- Steam Settings > System > **Enable Developer Mode**, then set a user
  password under Developer (SSH user `steamos`).
- Frame awake and worn, in its own home environment, controllers on and in
  view, local menu/dashboard closed.

### 2. Find the IP addresses

```powershell
ipconfig                  # PC, Windows: IPv4 of each wireless adapter
ip -brief -4 addr         # PC, Ubuntu; and on Frame (LXTerminal)
```

On Frame, `wlanap` is the **direct link** (preferred: about 1 ms round trip),
`wlan0` is home Wi‑Fi (works, but can stall for 100+ ms). Pick the PC adapter
on the same subnet. Ubuntu has no direct link yet (kernel 7.2+ needed). Details:
[non_pc_streaming/README.md](non_pc_streaming/README.md#network-home-wifi-or-direct-link).

### 3. Allow the packets through the firewall

```powershell
# Windows, once, in an administrator PowerShell (both Frame addresses in one rule)
New-NetFirewallRule -DisplayName "Frame pose UDP 9000" -Direction Inbound -Protocol UDP -LocalPort 9000 -RemoteAddress FRAME_WLAN0_IP,FRAME_WLANAP_IP -Action Allow
```

```sh
# Ubuntu, only if ufw is active (sudo ufw status)
sudo ufw allow from FRAME_WLAN0_IP to any port 9000 proto udp
sudo ufw allow from FRAME_WLANAP_IP to any port 9000 proto udp
```

Check SSH (no firewall rule needed):

```powershell
ssh steamos@FRAME_IP "python3 --version; uname -m"     # expect Python 3.12.x and aarch64
```

Optional: an SSH key removes the four password prompts per deploy
([how](non_pc_streaming/README.md#log-in-without-a-password-ssh-key-once)).

### 4. Run it

Window 1, the viewer:

```powershell
python -m general.visualize_poses --udp --sender-ip FRAME_IP
```

Window 2, the sender (`FRAME_IP` / `PC_IP` = the pair of the chosen path).
**First time, and after changing code or `config.toml`:** deploy, which uploads
to `~/frame_pose_sender` on Frame and runs:

```powershell
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -PcAddress PC_IP -Demo   # 1. network only
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -Probe -ProbeSeconds 30  # 2. what Frame exposes
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -PcAddress PC_IP         # 3. live, 90 Hz
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -PcAddress PC_IP -Hz 200 # other rate; -Hz 0 = unlimited
```

On Ubuntu, use the `tar`/`scp`/`ssh` commands in
[non_pc_streaming/README.md](non_pc_streaming/README.md#on-ubuntu-without-the-script).

**Afterwards:** the files stay on Frame, so run directly over SSH:

```powershell
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --hz 90"   # live; --hz 0 = unlimited
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --demo"    # network only
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m diagnostics.probe_controller --seconds 30"          # probe
```

- Ctrl+C stops the sender.
- Only one program can listen on UDP 9000 at a time: close the viewer before
  running a measurement tool.
- `--sync` (deploy: `-Sync`) is only for absolute-latency measurements.

### 5. Stop and clean up

```powershell
ssh steamos@FRAME_IP "pkill -f '[n]on_pc_streaming.frame_sender'; pkill -f '[d]iagnostics.probe_controller'"  # stop leftovers
ssh steamos@FRAME_IP "rm -rf ~/frame_pose_sender"                                                          # remove files
```

Everything lives in `~/frame_pose_sender`: no root, no system packages, no
background service. Packet format, coordinates and the rest:
[non_pc_streaming/README.md](non_pc_streaming/README.md).

## Benchmarks

Standalone over Frame's direct link delivers a pose about 1 ms after Frame
reads it, about 15 ms fresher than PC streaming; home Wi‑Fi works but can
stall for 150-400 ms. Full tables (Windows and Ubuntu), method and raw data:
[diagnostics/README.md](diagnostics/README.md#benchmarks).

## Tests

```powershell
python -B -m unittest discover -s general/tests -v     # keep UDP port 9000 free
```

## Dependencies and attribution

Bundled pyopenvr source and Valve's ARM64 OpenVR library retain their upstream
licenses; see [non_pc_streaming/vendor/PROVENANCE.md](non_pc_streaming/vendor/PROVENANCE.md).

Official Frame documentation:
- https://partner.steamgames.com/doc/steamhardware/steamframe/setup
- https://partner.steamgames.com/doc/steamhardware/steamframe/engines/custom
- https://partner.steamgames.com/doc/steamhardware/steamframe/debugging
