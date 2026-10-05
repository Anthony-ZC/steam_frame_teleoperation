# Steam Frame controller toolkit

Read, visualize and log Steam Frame controller data with Python: poses,
velocities, buttons with touch sensing, trigger/grip/thumbstick values,
finger curl and battery. Two ways to get the data to a Windows PC:

| Mode | How | PC needs | Status |
|---|---|---|---|
| **PC streaming** | PC SteamVR, while Frame streams to the PC | SteamVR + an active stream | verified |
| **Standalone** | a small Python sender runs **on Frame** and sends UDP packets | only this repository | verified (2026-10-04) |

The scripts collect and display data only. They do not control a robot.

## Contents

- [Setup](#setup) · [Folder structure](#folder-structure) · [Configuration](#configuration)
- [What the controllers expose](#what-the-controllers-expose) · [Viewer](#viewer)
- [PC streaming mode](#pc-streaming-mode) · [Standalone mode](#standalone-mode)
- [Benchmarks](#benchmarks) · [Tests](#tests) · [Dependencies and attribution](#dependencies-and-attribution)

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
```

If PowerShell refuses to run `Activate.ps1`, allow local scripts once with
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. All commands below
assume the environment is active (the prompt shows `(.venv)`), and run from
the repository root with `python -m`, so imports work across folders. The
headset side needs no installation: it uses Frame's Python 3.12, the standard
library and the bundled OpenVR library.

**Platforms:** tested on Windows 11 and, over home Wi‑Fi only, on Ubuntu 26.04
(PC streaming with SteamVR for Linux, standalone mode and every measurement
tool; see [Benchmarks](#benchmarks)). On Ubuntu the viewer needs a matplotlib
GUI backend in the venv (`pip install PyQt6`, or `sudo apt install python3-tk`),
otherwise it exits with "FigureCanvasAgg is non-interactive". Windows-only
parts: `non_pc_streaming/deploy_sender.ps1` (manual Linux commands
in [non_pc_streaming/README.md](non_pc_streaming/README.md#on-ubuntu-without-the-script))
and the Windows Firewall commands (Ubuntu: `ufw`, below).
`diagnostics/measure_stream_load.py` reads `/proc` on Linux (no per-engine GPU
split). Ubuntu over home Wi‑Fi: `diagnostics/run_ubuntu_wifi_benchmark.sh`.

## Folder structure

```text
config.toml                Field selection, relative pose mode, OpenVR app type
general/                   Shared by both modes
  visualize_poses.py       Viewer: 3D relative pose + hand/controller panels
  openvr_sampler.py        OpenVR sampling, used on the PC and on Frame (numpy-free)
  clock_sync.py            Optional Frame/PC clock sync for absolute latency (numpy-free)
  controller_state.py      ControllerState: pose, velocity, buttons, fingers (numpy-free)
  pose_wire.py             UDP packet formats FVR1 (poses) and FVR2 (+ optional groups)
  relative_pose.py         Relative pose after a settle delay, reset
  readers.py, demo.py      Reader base class, demo reader, synthetic states
  poses.py, config.py      Pose model (numpy), config.toml loader
  input/                   SteamVR Input action manifest + bindings (make_manifest.py)
  tests/                   Unit and loopback tests
streaming/                 PC streaming mode
  frame_pose.py            SteamVRReader (OpenVR on the PC)
  read_poses.py            Console output and CSV logging
non_pc_streaming/          Standalone mode
  frame_sender.py          Sender running on Frame (--demo, --desktop, --hz 0)
  udp_pose.py              UDP receiver on the PC
  deploy_sender.ps1        Package, upload and run on Frame (-Demo, -Probe, -Hz)
  vendor/                  Bundled ARM64 OpenVR library and licenses
diagnostics/               Probes and measurements, not used by the runtime code
  probe_controller.py      What each controller exposes (PC or Frame)
  measure_stream_load.py   PC load + pose stability per setup
  measure_udp_rate.py      UDP rate, loss, jitter, tracking updates
  measure_latency.py       Relative/absolute latency standalone vs. streaming
  measure_pose_rate.py     Pose-change frequency from PC SteamVR
  diagnose_tracking.py     Background vs. scene app tracking
  benchmark_plan.md        Benchmark procedure (for reruns)
  results/                 Raw results behind the README benchmark tables
artifacts/                 Generated previews, packages, measurements (ignored by Git)
```

Each folder has its own README with details.

## Configuration

`config.toml` (or `--config PATH`) is read by the viewer, the logger and the
Frame sender (it is deployed with it):

- `[fields]` turns data groups on or off: `velocity`, `battery`, `buttons`,
  `analog`, `fingers`. The pose is always included. With `buttons`, `analog`
  and `fingers` all off, SteamVR Input is never initialized. In standalone mode
  the sender transmits exactly the enabled groups.
- `[relative_pose]`: `enabled`, `mode` (`own_frame`: `T0^-1 * T`, motion in the
  controller's initial frame; `world_axes`: `p - p0` and `R * R0^T` along
  SteamVR standing axes), `settle_seconds`.
- `[input]`: `app_type` (`background`, `overlay`, `scene`) and `legacy_fallback`.

## What the controllers expose

Verified for both Frame controllers (`frame_controller`), in both modes:

| Group | Data | Source |
|---|---|---|
| pose | 3x4 transform, tracking result | IVRSystem |
| velocity | linear and angular velocity | IVRSystem |
| battery | battery level, charging, controller type | device properties |
| buttons | A/B/X/Y (left: mirrored d-pad), menu/view, bumper, thumbstick, trigger, grip: click + touch; thumbrest and system: touch (system click is reserved by SteamVR) | SteamVR Input |
| analog | trigger, grip, thumbstick x/y | SteamVR Input |
| fingers | curl x5, splay x4 (skeletal level: partial) | SteamVR Input skeleton |

**Close the SteamVR dashboard in the headset.** While it is open (for example
showing the streamed desktop) it receives all controller input, and every
other app's buttons, analog values and fingers go inactive; poses still
arrive. The viewer, probe and sender say when this happens.

Check a controller yourself (touch, press and squeeze everything while it runs):

```powershell
python -m diagnostics.probe_controller --seconds 20
```

The legacy controller state returns nothing for a background app, so SteamVR
Input (`general/input/actions.json`) is the working path. Bindings ship for
`frame_controller` and `knuckles`; regenerate them with
`python -m general.input.make_manifest`.

## Viewer

```powershell
python -m general.visualize_poses            # PC streaming
python -m general.visualize_poses --udp --sender-ip FRAME_IP   # standalone
python -m general.visualize_poses --demo     # synthetic, no hardware
```

- **3D view:** each controller's pose relative to a reference captured
  `settle_seconds` (default 3 s) after launch; hold the controllers still
  during the countdown. **Reset Pose** (or `R`) recaptures the reference. A
  controller that appears later is referenced on first sight and keeps its
  reference through tracking loss.
- **One panel per hand:** five finger-curl bars (thumb to pinky; shade =
  splay) beside a controller sketch with bumper, menu/view, system, thumbrest,
  trigger and grip (with analog fill), thumbstick position and the face
  buttons. Lamps are grey when idle, outlined when **touched**, filled when
  **pressed**, dotted when there is no data. Text shows relative position,
  roll/pitch/yaw, speed, battery, tracking and input source.
- Targets 90 Hz with partial redraws. `--hz`, `--span` (view width in m) and
  `--full-redraw` adjust it; `--demo --benchmark 120` reports render speed.

## PC streaming mode

1. Start SteamVR on the PC and stream from Frame (a minimized desktop is enough).
2. **Close the SteamVR dashboard** in the headset.
3. Keep both controllers awake and in view of the headset's cameras.

```powershell
python -m general.visualize_poses
python -m streaming.read_poses --csv artifacts/poses.csv
```

`read_poses` prints poses and inputs and logs CSV (columns follow `[fields]`;
`pose_frame` says whether a row is absolute or relative). See
[streaming/README.md](streaming/README.md).

With the stream off, SteamVR still reports the controllers as tracked but their
poses stop changing; a frozen pose is not yet flagged as lost tracking.

## Standalone mode

The sender runs on Frame, reads Frame's own VR runtime and sends UDP packets
to the PC. No PC stream and no PC SteamVR are needed.

### Requirements

- On Frame: Steam Settings > System > **Enable Developer Mode**, then set a
  user password under Developer (SSH user `steamos`).
- Frame awake and worn, in its own home environment, controllers on and in
  view, local menu/dashboard closed.
- Frame and PC on a common network (see below).

### Find the IP addresses

On the **PC**, run `ipconfig` (Windows) or `ip -brief -4 addr` (Ubuntu) and
note the IPv4 address of each wireless adapter. On **Frame**, open a terminal
(LXTerminal) and run:

```sh
ip -brief -4 addr
```

Frame typically shows these interfaces:

| Frame interface | What it is | Matching PC adapter |
|---|---|---|
| `wlan0` | Frame as a normal client of your home Wi‑Fi | the PC adapter on the same router subnet (it has a default gateway) |
| `wlanap` | Frame's own access point: the **direct link**, used by PC streaming together with Wi‑Fi | the PC adapter on the same subnet, with **no** default gateway (e.g. `Wi-Fi 6`) |
| `usb0` | networking over a USB cable, if connected | – |

Addresses from DHCP can change; check again if a connection stops working.

### Home Wi‑Fi or direct link?

| | Home Wi‑Fi (`wlan0`) | Direct link (`wlanap`) |
|---|---|---|
| Path | Frame → router → PC | Frame → PC, no router |
| Round trip (ping) | about 4 ms avg, up to 18 ms | about 1 ms avg, up to 5 ms |
| Delay variation (p99) | 4-6 ms in good runs, **130+ ms** in bad ones | about 3 ms in every run |
| Worst stall | up to about 190 ms (in 2 of 6 runs) | about 20-40 ms |
| Needs | both devices on the same router | the PC's streaming adapter connected to Frame (stayed up with PC SteamVR closed) |

**Use the direct link** when it is available. Both deliver every packet and
the same tracking rate; details in the
[benchmarks](#data-rate-and-timing-streaming-vs-standalone).

**Ubuntu: no direct link yet** (2026-10-05, Ubuntu 26.04, kernel 7.0). Frame's
hotspot only uses 6 GHz, and Linux disables every 6 GHz channel while the
Wi‑Fi region is unset (`iw reg get` shows `country 00`), so the adapter could
not even see Frame. Setting the region fixes that, now and after reboots:

```sh
sudo iw reg set US                                                              # now
echo 'options cfg80211 ieee80211_regdom=US' | sudo tee /etc/modprobe.d/cfg80211-regdom.conf  # at boot
```

(Use your own country code; undo with `sudo rm /etc/modprobe.d/cfg80211-regdom.conf`
and a reboot.) The adapter (`rtw89_8852cu`) then sees Frame's hotspot, but
joining still fails in the driver (`failed to insert STA entry for the AP
(error -22)`): Valve requires kernel 7.2 or newer for this adapter. The
region setting stays in place for then; until Ubuntu ships such a kernel, use
home Wi‑Fi for both streaming and standalone.

### Allow the packets through the firewall

**Ubuntu** (only if `ufw` is active; check with `sudo ufw status`):

```sh
sudo ufw allow from FRAME_WLAN0_IP to any port 9000 proto udp
sudo ufw allow from FRAME_WLANAP_IP to any port 9000 proto udp
```

**Windows**, once, in an **administrator** PowerShell (both Frame addresses in one rule):

```powershell
New-NetFirewallRule -DisplayName "Frame pose UDP 9000" -Direction Inbound -Protocol UDP -LocalPort 9000 -RemoteAddress FRAME_WLAN0_IP,FRAME_WLANAP_IP -Action Allow
```

Update it if Frame's address changes (`Set-NetFirewallRule -DisplayName "Frame pose UDP 9000" -RemoteAddress ...`),
remove it with `Remove-NetFirewallRule -DisplayName "Frame pose UDP 9000"`.
SSH needs no rule (outgoing from the PC). Check that you can log in:

```powershell
ssh steamos@FRAME_IP "python3 --version; uname -m"     # expect Python 3.12.x and aarch64
```

### Optional: log in without a password (SSH key, once)

Without a key, every `ssh`/`scp` call asks for the Frame password, and one
deploy makes four of them (create folder, upload, extract and check, run). An
SSH key removes all prompts. Once, on the PC:

```powershell
ssh-keygen -t ed25519      # press Enter at the prompts (a passphrase is optional)
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh steamos@FRAME_IP "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

On Ubuntu: `ssh-keygen -t ed25519`, then `ssh-copy-id steamos@FRAME_IP`. The
last command asks for the password one final time. The key then works for both
Frame addresses (same headset, same user).

### Run it

Window 1, the viewer:

```powershell
python -m general.visualize_poses --udp --sender-ip FRAME_IP
```

Window 2 starts the sender (`FRAME_IP` / `PC_IP` = the pair of the chosen path,
e.g. the `wlanap` address and the PC's direct-link address).

**First time, and after changing code or `config.toml`:** deploy. The script
uploads the code and `config.toml` to `~/frame_pose_sender` on Frame, then runs:

```powershell
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -PcAddress PC_IP -Demo   # 1. network only
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -Probe -ProbeSeconds 30  # 2. what Frame exposes
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -PcAddress PC_IP         # 3. live, 90 Hz
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_IP -PcAddress PC_IP -Hz 200 # other rate; -Hz 0 = unlimited
```

**Afterwards:** the files stay on Frame, so run directly over SSH without
uploading (one connection, one password prompt or none with a key):

```powershell
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --hz 90"   # live; --hz 0 = unlimited
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --demo"    # network only
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m diagnostics.probe_controller --seconds 30"          # probe
```

Add `--sync` (deploy script: `-Sync`) only for absolute-latency measurements;
it answers clock-sync requests from the PC on UDP 9001 (see
[Latency](#latency)). Normal use needs no flag and opens no extra port.

Ctrl+C stops the sender. Only one program can listen on UDP 9000 at a time
(close the viewer before running a measurement tool). The deploy script is
Windows PowerShell; on Ubuntu use the equivalent `tar`/`scp`/`ssh` commands in
[non_pc_streaming/README.md](non_pc_streaming/README.md#on-ubuntu-without-the-script).

To test the whole UDP path on the PC first, against PC SteamVR:

```powershell
python -m non_pc_streaming.frame_sender --desktop --pc 127.0.0.1
```

### Stop and clean up

```powershell
ssh steamos@FRAME_IP "pgrep -af '[n]on_pc_streaming.frame_sender|[d]iagnostics.probe_controller'"        # what runs
ssh steamos@FRAME_IP "pkill -f '[n]on_pc_streaming.frame_sender'; pkill -f '[d]iagnostics.probe_controller'"  # stop all
ssh steamos@FRAME_IP "rm -rf ~/frame_pose_sender"                                                          # remove files
```

The sender normally ends with its SSH session; leftovers come from a second
deploy window. Everything lives in `~/frame_pose_sender`: no root, no system
packages, no background service. Deployment details, packet format and
coordinates: [non_pc_streaming/README.md](non_pc_streaming/README.md).

## Benchmarks

Test PC: Intel Core Ultra 7 270K Plus (24 cores), 48 GB RAM, NVIDIA GeForce
RTX 5090 (32 GB), SteamVR build 1789498647, measured with the tools in
[diagnostics/](diagnostics/README.md). Two runs on this PC:

- **Windows 11 Pro** 10.0.26200, NVIDIA driver 617.14, 2026-10-04: direct link
  and home Wi‑Fi. The sections from [PC load](#pc-load-and-pose-stability)
  to [Clock sync method](#clock-sync-method).
- **Ubuntu 26.04.1**, kernel 7.0, NVIDIA driver 595.91.07, 2026-10-05: home
  Wi‑Fi only ([no direct link yet](#home-wifi-or-direct-link)), same tools,
  same tables: [Ubuntu, home Wi‑Fi](#ubuntu-home-wifi).

[Windows vs. Ubuntu](#windows-vs-ubuntu) at the end compares them. The raw
results behind every table are in
[diagnostics/results/](diagnostics/results/README.md).

### PC load and pose stability

`diagnostics.measure_stream_load`, 20 s per streaming run (desktop stream, both
controllers, pose-only polling from a background OpenVR app). The standalone
column is the Frame sender over the direct link at 200 Hz, PC SteamVR closed,
30 s; its pose rows are UDP arrival (see [Data rate](#data-rate-and-timing-streaming-vs-standalone)).

| | Stream off | Stream, dashboard open | Stream, dashboard closed | Standalone (no stream) |
|---|---|---|---|---|
| CPU total, mean / p95 | 10.6% / 15.9% | 21.9% / 34.1% | 14.9% / 19.4% | 12.5% / 19.1% |
| SteamVR/Steam processes CPU (of all cores) | 0.5% | 1.9% | 1.7% | 0% |
| GPU 3D, mean | 0.4% | 6.3% | 5.1% | 2.5% |
| GPU VideoEncode / NVENC utilization | 0% | 12% | 12% | 0% |
| NVENC sessions, average fps | 1, 0 fps | 1, 182 fps | 1, 183 fps | 0 |
| Pose changes per controller (incl. extrapolated) | **0 (frozen)** | 615 Hz | 614 Hz | 200 Hz |
| Natural tracking rate (real samples) | - | - | ≈ 217 Hz | ≈ 233 Hz |
| Pose interval median / p95 / max | - | 1.6 / 1.8 / 8.8 ms | 1.6 / 1.8 / 8.5 ms | 5.0 / 6.4 / 17.5 ms |
| Gaps > 3x median (per run) | - | 1 | 1 | 4 |
| Buttons, analog, finger curl | - | **blocked** | available | available |

- Keeping the stream alive is cheap on this PC: about 12% of one NVENC encoder,
  about 5% GPU 3D and about 1.2% CPU in SteamVR processes. Total CPU varies
  with other programs; the SteamVR-process figure is the reliable one.
- Streaming: use it with the **dashboard closed**; same cost, but the open
  dashboard takes all controller input.
- Standalone removes the streaming cost entirely: no encoder session, no
  SteamVR processes.
- The 614 Hz is the script's polling rate: SteamVR returns a newly predicted
  pose on every call. The natural tracking rates come from the
  [data rate table](#data-rate-and-timing-streaming-vs-standalone). With the stream
  off, poses froze while still reported as tracked.

### Data rate and timing: streaming vs. standalone

Both modes measured with the same tool (`measure_udp_rate`) and the same
packets: both controllers moving, every `[fields]` group, 30 s per run,
dashboard closed.

- **Streaming**: PC SteamVR with the Frame stream; sender on the PC
  (`frame_sender --desktop`) over loopback. The Frame-to-PC part travels
  inside SteamVR's link and is not visible.
- **Standalone, direct link**: sender on Frame, from its `wlanap` access point
  to the PC's direct-link adapter; stream off, PC SteamVR closed.
- **Standalone, home Wi‑Fi**: sender on Frame, from `wlan0` via the router to
  the PC's home Wi‑Fi adapter; stream off, PC SteamVR closed.

| Setup | Send rate | Packets received | Real tracking samples | Sample interval median / p95 | Packet interval median / p99 / max | Lost packets | Delay variation median / p99 / max |
|---|---|---|---|---|---|---|---|
| Streaming | 100 Hz | 100 Hz | 100 Hz | 10.0 / 10.3 ms | 10.0 / 10.5 / 10.6 ms | 0 | 0.04 / 0.15 / 0.28 ms (loopback) |
| Streaming | 200 Hz | 200 Hz | 168-171 Hz | 5.1 / 10.1 ms | 5.0 / 5.6 / 5.9 ms | 0 | 0.04 / 0.13 / 0.25 ms (loopback) |
| Streaming | unlimited | 4525 Hz | **≈ 217 Hz** | 4.5 / 8.5 ms | 0.2 / 0.4 / 38.5 ms | 0 | 0.01 / 0.14 / 38.3 ms (loopback) |
| Standalone, direct link | 100 Hz | 100 Hz | 99.8-99.9 Hz | 10.0 / 11.5 ms | 10.0 / 12.7 / 32.9 ms | 0 | 0.57 / 3.3 / 22.8 ms |
| Standalone, direct link | 200 Hz | 200 Hz | 174-175 Hz | 5.1 / 10.3 ms | 5.0 / 7.2 / 40.7 ms | 0 | 0.53 / 2.9 / 36.7 ms |
| Standalone, direct link | unlimited | 2464 Hz | **≈ 233 Hz** | 4.1 / 8.1 ms | 0.03 / 2.1 / 20.1 ms | 3 of 73,886 | 1.29 / 3.4 / 31.4 ms |
| Standalone, home Wi‑Fi | 100 Hz | 100 Hz | 99.7-99.8 Hz | 10.0 / 11.5 ms | 10.0 / 55.6 / **185.7** ms | 0 | 1.20 / **134.0 / 177.5** ms |
| Standalone, home Wi‑Fi | 200 Hz | 200 Hz | 174-177 Hz | 5.1 / 10.2 ms | 5.0 / 7.4 / 26.6 ms | 0 | 1.47 / 3.8 / 22.9 ms |
| Standalone, home Wi‑Fi | unlimited | 2523 Hz | **≈ 233 Hz** | 4.1 / 8.3 ms | 0.03 / 3.0 / 23.7 ms | 0 | 2.03 / 6.1 / 26.3 ms |

What the columns mean:

- **Send rate**: how often the sender reads the controllers and sends a
  packet (`--hz`); unlimited = as fast as it can.
- **Packets received**: packets per second arriving at the PC.
- **Real tracking samples**: packets per second, per controller, that carry a
  *new* tracking sample. Both runtimes extrapolate the position between
  samples, but the velocity only changes with a real sample, so this counts
  velocity changes. It cannot exceed the runtime's natural tracking rate.
- **Sample interval**: time between two real tracking samples.
- **Packet interval**: time between two packets arriving at the PC; the max is
  the longest stall.
- **Lost packets**: missing sequence numbers.
- **Delay variation**: how much later each packet arrived than the fastest
  packet of the run. It shows jitter and stalls without clock sync; it is not
  the latency itself (see [Latency](#latency)).

At the unlimited rate Wi‑Fi delivers packets in batches, so the median packet
interval is tiny (0.03 ms) and says little. Network round trip PC ↔ Frame
(`ping`, 40 samples, min / avg / max): direct link 1 / 1 / 5 ms, home Wi‑Fi
3 / 4 / 18 ms.

Findings:

- **Natural tracking rate**: about 217 Hz through PC streaming, about 233 Hz
  from Frame's local runtime (one real sample every 4-4.5 ms).
- **100 Hz** gives a real sample in practically every packet in both modes.
  **200 Hz** is close to the natural rate, so the two clocks drift against each
  other and 13-16% of packets repeat the previous sample. To get every sample,
  send faster than the natural rate (unlimited); to get regular packets, stay
  well below it.
- Standalone pays for its network hop with jitter (direct link: delay
  variation p99 about 3 ms, rare spikes of 20-40 ms); in streaming that part
  is hidden inside SteamVR.
- **Home Wi‑Fi is unpredictable.** Same tracking rate as the direct link (it
  comes from Frame), but 2 of the 6 home Wi‑Fi runs in this README (this
  table and [absolute latency](#absolute-latency)) had stalls of 150-190 ms,
  independent of the rate. The direct link never did. **Use the direct link**;
  on home Wi‑Fi, a robot controller must tolerate such stalls.

### Latency

All latencies are measured on the **pose**. Buttons, analog values and
fingers are read in the same sampling call as the pose and travel in the same
packet, so in standalone mode they have the same latency to the PC. Not
measured: how long a button press takes to reach the runtime's input state,
and the input path through PC streaming.

#### Absolute latency

Frame and PC clocks are synchronized during the run (method below), so each
standalone packet's travel time can be measured directly: **PC arrival − the
moment Frame read the pose**.

**Standalone** (stream off, PC SteamVR closed; `measure_udp_rate --sync`):

| Path | Send rate | Median | p95 | p99 | Max | Sync error bound | Sample age at read, up to |
|---|---|---|---|---|---|---|---|
| Direct link | 100 Hz | 1.01 ms | 2.13 ms | 2.59 ms | 8.6 ms | ±0.68 ms | 10 ms |
| Direct link | 200 Hz | 1.00 ms | 2.12 ms | 4.65 ms | 33.8 ms | ±0.50 ms | 5 ms |
| Direct link | unlimited (about 2300 Hz) | 1.24 ms | 2.03 ms | 3.09 ms | 22.3 ms | ±0.55 ms | 0.44 ms |
| Home Wi‑Fi | 100 Hz | 3.02 ms | 11.2 ms | 35.6 ms | 46.6 ms | ±1.43 ms | 10 ms |
| Home Wi‑Fi | 200 Hz | 3.09 ms | **68.3 ms** | **146.7 ms** | **175.6 ms** | ±1.41 ms | 5 ms |
| Home Wi‑Fi | unlimited (about 2450 Hz) | 2.39 ms | 3.98 ms | 5.52 ms | 22.0 ms | ±1.45 ms | 0.42 ms |

- **Median … Max**: packet travel time, pose read on Frame → arrival at the PC.
- **Sync error bound**: accuracy of the clock sync for that run.
- **Sample age at read**: a new tracking sample can wait up to one send
  interval on Frame before the sender reads it (median value). Add it to the
  travel time for the worst-case age of a fresh sample.

No packet was lost. Over the direct link at the unlimited rate, a new tracking
sample reaches the PC in about 1.3-1.7 ms.

**Streaming** (stream on; `measure_latency --sync` runs both pipelines at
once, the Frame sender over the direct link). Streaming latency = how far PC
SteamVR's pose lags the moment Frame read the same motion:

| Frame sender rate | Streaming latency, left / right | Standalone travel time, median (p95) | Correlation, streaming | Sync error bound |
|---|---|---|---|---|
| 100 Hz | +17.2 / +17.3 ms | 1.87 ms (3.46 ms) | 1.00 / 1.00 | ±0.52 ms |
| 200 Hz | +17.0 / +17.2 ms | 1.88 ms (3.01 ms) | 1.00 / 1.00 | ±0.42 ms |
| unlimited | +3.2 / +3.1 ms | 1.84 ms (2.96 ms) | 1.00 / 0.99 | ±0.52 ms |

Correlation (1.00 = identical motion traces) shows the match is reliable.
Streaming latency is one value per controller and run, not a distribution
(no min, p95/p99, max or variation): PC SteamVR's poses carry no timestamp of
when Frame captured them, so the lag is found by shifting the whole 20 s speed
trace against Frame's read-time trace until they match best. A spread would
need the same match in short sliding windows (not implemented).
Standalone is slower here than above (1.9 vs. 1.0 ms) because the packets
share the direct link with the video stream.

Findings:

- **Standalone over the direct link delivers a pose about 1 ms after Frame
  reads it**; home Wi‑Fi about 2.4-3.1 ms at the median, with an
  unpredictable tail.
- **PC streaming shows a motion about 17 ms after Frame's runtime has it**,
  so standalone data is about 15 ms fresher.
- With the Frame sender at the unlimited rate, streaming lagged only about
  3 ms. A repeat run at 100 Hz and at unlimited gave the same result; the
  cause is unknown.

#### Relative latency

The earlier method, without clock sync: both pipelines run at once on the
same hand motion, both timestamped on arrival at the PC, and the
controllers' speed traces are cross-correlated (`measure_latency`). Streaming
(PC SteamVR, polled at about 930 Hz) is the reference.

| Standalone path | Standalone send rate | Standalone vs. streaming, left | Right | Correlation, left / right |
|---|---|---|---|---|
| Direct link | 100 Hz | −15.2 ms | −1.9 ms | 0.99 / 0.98 |
| Direct link | 200 Hz | +2.6 ms | −15.1 ms | 0.97 / 0.99 |
| Direct link | unlimited (about 2900 Hz) | −1.9 ms | −7.4 ms | 1.00 / 0.98 |

A negative value means standalone arrives earlier than streaming. All six
values lie between 15.2 ms earlier and 2.6 ms later (mean about 6.5 ms
earlier): standalone is at least as fast. The values jump by about 15 ms
between runs and hands; the absolute measurement above shows that this jump
comes from the streaming side. Home Wi‑Fi was not measured this way.

#### Other latency figures

| What | Result |
|---|---|
| Network round trip PC ↔ Frame (`ping`, 40 samples) | direct link 1 / 1 / 5 ms, home Wi‑Fi 3 / 4 / 18 ms (min / avg / max) |
| Loopback latency, sender on the PC (same clock) | 0.06-0.12 ms median |
| Motion-to-data latency (hand moves → data) | not measured; needs an external reference such as high-speed video |

#### Clock sync method

The packet timestamp is the moment Frame read the poses, on Frame's clock.
With the sender started with `--sync`, the measurement tools exchange
NTP-style timestamps with Frame during the run (repeated bursts, drift
fitted) and map Frame times onto the PC clock. Accuracy is ± half the
fastest round trip, reported with each result; verified on loopback (offset
+0.003 ms against a true 0, bound ±0.02 ms). Both runtimes extrapolate poses
to "now", so these are *effective* latencies, as seen by whoever receives the
data; the tracking work inside the runtime (camera exposure, fusion) happens
before the Frame read and is not included.

### Ubuntu, home Wi‑Fi

Same PC, same tools and settings as the Windows tables above, following the
[Ubuntu procedure](diagnostics/benchmark_plan.md#ubuntu-home-wifi-only).
There is no direct link on Ubuntu yet, so **every path uses home Wi‑Fi only**:
the PC stream (Windows: Valve's combined streaming over the direct link plus
Wi‑Fi) and the standalone sender. Raw results: [diagnostics/results/ubuntu_wifi/](diagnostics/results/README.md).

Network round trip PC ↔ Frame (`ping`, 40 samples, min / avg / max): 5 / 11 /
84 ms; two other checks that day gave 2.8 / 4.3 / 6.5 ms (20 samples) and
4.7 / 16.8 / 106 ms (40 samples).

**Stream stability.** The Wi‑Fi stream dropped at least three times in about
20 minutes (once seconds after starting, once with a SteamVR crash that
restarted it in safe mode, once between two runs), and SteamVR logged 0-4 video resets ("frame ID was not what
we expected") per streaming run. Each run was checked against the vrlink log;
the two runs during which the stream dropped were discarded and repeated.

#### Ubuntu: PC load and pose stability

`measure_stream_load`, 20 s per streaming run; standalone column: Frame sender
over home Wi‑Fi at 200 Hz, PC SteamVR closed, 30 s, its pose rows from UDP
arrival.

| | Stream off | Stream, dashboard open | Stream, dashboard closed | Standalone (no stream) |
|---|---|---|---|---|
| CPU total, mean / p95 | 2.6% / 9.1% | 2.9% / 10.2% | 2.6% / 9.5% | 1.7% / 2.0% |
| SteamVR/Steam processes CPU (of all cores) | 0.51% | 1.56% | 1.24% | 0.14% |
| GPU, whole chip (`nvidia-smi`), mean | 7.2% | 8.6% | 8.3% | 4.2% |
| Video encoder utilization | 0% | 31% | 30% | 0% |
| Pose changes per controller (incl. extrapolated) | **0 (frozen)** | 807 Hz | 829 Hz | 200 Hz |
| Natural tracking rate (real samples) | - | - | ≈ 197 Hz | ≈ 231 Hz |
| Pose interval median / p95 / max | - | 1.2 / 1.4 / **185** ms | 1.2 / 1.3 / 62 ms | 4.2 / 6.6 / **254** ms |
| Gaps > 3x median (per run) | - | 9 | 15 | 177 |

- SteamVR for Linux encodes with Vulkan Video, not the NVENC API:
  `nvidia-smi` shows the encoder busy but no NVENC session or fps, and Linux
  has no per-engine GPU split (the Windows "GPU 3D" row). Encoder use is
  about 30%, against 12% on Windows.
- Keeping the stream alive costs about 0.7% CPU in SteamVR processes (stream
  off 0.51%, dashboard closed 1.24%; Windows: about 1.2%).
- PC SteamVR's poses stall for up to 60-185 ms: the controller data reaches
  the PC over the same Wi‑Fi as the video (Windows, direct link + Wi‑Fi:
  8.5 ms).

#### Ubuntu: Data rate and timing

`measure_udp_rate`, 30 s per run, both controllers moving, every `[fields]`
group, dashboard closed. Streaming: sender on the PC against PC SteamVR, over
loopback, with Frame streaming over home Wi‑Fi. Standalone: sender on Frame,
via the router; stream off, PC SteamVR closed.

| Setup | Send rate | Packets received | Real tracking samples | Sample interval median / p95 | Packet interval median / p99 / max | Lost packets | Delay variation median / p99 / max |
|---|---|---|---|---|---|---|---|
| Streaming | 100 Hz | 100 Hz | **86-87 Hz** | 10.0 / 19.8 ms | 10.0 / 10.7 / 11.9 ms | 0 | 0.27 / 0.44 / 0.64 ms (loopback) |
| Streaming | 200 Hz | 200 Hz | **149-150 Hz** | 5.0 / 10.1 ms | 5.0 / 5.3 / 5.8 ms | 0 | 0.18 / 0.28 / 0.57 ms (loopback) |
| Streaming | unlimited | 6755 Hz | **≈ 197 Hz** | 4.5-4.6 / 9.6 ms | 0.15 / 0.32 / 23.0 ms | 0 | 0.00 / 0.20 / 22.9 ms (loopback) |
| Standalone, home Wi‑Fi | 100 Hz | 100 Hz | 99.7-99.9 Hz | 9.4 / 35.0 ms | 9.4 / 112.7 / **229.1** ms | 0 | 1.92 / **143.3 / 220.5** ms |
| Standalone, home Wi‑Fi | 200 Hz | 200 Hz | 175.6-175.8 Hz | 4.3 / 10.5 ms | 4.1 / 102.8 / **214.2** ms | 0 | 2.27 / **172.7 / 210.7** ms |
| Standalone, home Wi‑Fi | unlimited | 2560 Hz | **≈ 231 Hz** | 1.8-1.9 / 8.4-8.7 ms | 0.04 / 2.9 / **284.1** ms | **564 of 77,355** | 2.29 / **247.8 / 410.9** ms |

Columns as in the [Windows table](#data-rate-and-timing-streaming-vs-standalone).

- Frame's own tracking rate is unchanged (standalone: about 231 Hz, 175 Hz
  at a 200 Hz send rate), but **every** standalone run stalled for 200-410 ms,
  and the unlimited rate lost 0.7% of packets.
- Streaming delivers fewer real samples than on Windows (86 / 150 / 197 Hz
  against 100 / 170 / 217 Hz): when the Wi‑Fi stalls, PC SteamVR keeps
  extrapolating, and samples lost on the way never arrive.

#### Ubuntu: Absolute latency

**Standalone** (stream off, PC SteamVR closed; `measure_udp_rate --sync`):

| Path | Send rate | Median | p95 | p99 | Max | Sync error bound | Sample age at read, up to |
|---|---|---|---|---|---|---|---|
| Home Wi‑Fi | 100 Hz | 3.39 ms | **89.6 ms** | **119.5 ms** | **200.0 ms** | ±1.38 ms | 10 ms |
| Home Wi‑Fi | 200 Hz | 4.27 ms | **119.1 ms** | **183.2 ms** | **251.8 ms** | ±1.36 ms | 5 ms |
| Home Wi‑Fi | unlimited (about 2500 Hz) | 2.84 ms | **95.3 ms** | **162.1 ms** | **212.8 ms** | ±1.32 ms | 0.43 ms |

311 of about 75,800 packets were lost at the unlimited rate, none at 100 and
200 Hz.

**Streaming** (stream on over home Wi‑Fi; `measure_latency --sync`, the Frame
sender over the same Wi‑Fi):

| Frame sender rate | Streaming latency, left / right | Standalone travel time, median (p95) | Correlation, streaming | Sync error bound |
|---|---|---|---|---|
| 100 Hz | +5.8 / +1.3 ms | 3.23 ms (84.1 ms) | 0.96 / 0.97 | ±1.35 ms |
| 200 Hz | +16.6 / +10.6 ms | 3.77 ms (151.3 ms) | 0.80 / 0.74 | ±1.41 ms |
| unlimited | +12.5 / +22.8 ms | 3.65 ms (59.9-62.7 ms) | 0.68 / 0.76 | ±1.48 ms |

- Standalone over home Wi‑Fi: about 3-4 ms at the median, as on Windows,
  but a p95 of 60-150 ms in every run.
- Streaming latency: 1-23 ms, with weaker trace matches than on Windows
  (0.68-0.97 against 1.00), because both traces have Wi‑Fi gaps. Treat the
  200 Hz and unlimited values as rough (about ±5-10 ms). The Windows pattern
  (17 ms at 100/200 Hz, 3 ms at unlimited) did not reappear.

#### Ubuntu: Relative latency

`measure_latency` without clock sync, Frame sender over home Wi‑Fi, streaming
(PC SteamVR, polled at about 1550-1600 Hz) as the reference:

| Standalone path | Standalone send rate | Standalone vs. streaming, left | Right | Correlation, left / right |
|---|---|---|---|---|
| Home Wi‑Fi | 100 Hz | −0.4 ms | −0.6 ms | 0.88 / 0.91 |
| Home Wi‑Fi | 200 Hz | +0.0 ms | −2.1 ms | 0.87 / 0.84 |
| Home Wi‑Fi | unlimited (about 2700 Hz) | +0.5 ms | −2.6 ms | 0.91 / 0.96 |

All six values lie between 2.6 ms earlier and 0.5 ms later: with both modes
on the same Wi‑Fi, standalone arrives about as early as streaming. (The 200 Hz
run is a `measure_latency --sync` attempt whose sender was started without
`--sync`; without sync replies it is exactly this measurement.)

### Method notes

- The PC load table's streaming pose rows come from local polling, the
  standalone column from UDP arrival; the
  [data rate](#data-rate-and-timing-streaming-vs-standalone) table uses the
  same method for both modes. The procedure is in
  [diagnostics/benchmark_plan.md](diagnostics/benchmark_plan.md).
- Both runtimes extrapolate poses: a changed position is not proof of a new
  tracking sample; velocity changes are.
- One run per configuration and operating system, on one PC and one network;
  rerun on other hardware before generalizing.

### Windows vs. Ubuntu

Same PC, headset, SteamVR build and tools; the networks differ. On Windows
the stream used Valve's combined streaming over the direct link plus Wi‑Fi; on
Ubuntu everything used home Wi‑Fi alone, which was also slower on the Ubuntu
day (round trip max 84-106 ms against 18 ms). A
difference below is therefore mostly **network**, not operating system,
unless it does not cross the Wi‑Fi (tracking rate, PC load).

| What | Windows | Ubuntu (home Wi‑Fi only) |
|---|---|---|
| Ping PC ↔ Frame, min / avg / max | direct link 1 / 1 / 5 ms; home Wi‑Fi 3 / 4 / 18 ms | home Wi‑Fi 5 / 11 / 84 ms |
| **Standalone, home Wi‑Fi** | | |
| Latency, median | 2.4-3.1 ms | 2.8-4.3 ms |
| Latency, p99 | 5.5-147 ms | 119-183 ms |
| Worst stall (delay variation or latency max) | 22-186 ms | 200-411 ms |
| Runs with stalls > 100 ms | 2 of 6 | 6 of 6 |
| Lost packets | 0 | 0 at 100/200 Hz; 0.4-0.7% at unlimited |
| Real tracking samples at 100 / 200 Hz / unlimited | 100 / 174-177 / ≈ 233 Hz | 100 / 175-176 / ≈ 231 Hz |
| **Streaming** (Windows: direct link + Wi‑Fi; Ubuntu: Wi‑Fi only) | | |
| Real tracking samples at 100 / 200 Hz / unlimited | 100 / 168-171 / ≈ 217 Hz | 86-87 / 149-150 / ≈ 197 Hz |
| Streaming latency at 100 / 200 Hz / unlimited | +17 / +17 / +3 ms (correlation 1.00) | +1-6 / +11-17 / +13-23 ms (correlation 0.68-0.97) |
| Standalone vs. streaming (relative) | −15.2 to +2.6 ms | −2.6 to +0.5 ms |
| PC SteamVR pose interval max, dashboard closed | 8.5 ms | 62 ms |
| Stream drops during the session | not recorded | at least 3, one with a SteamVR crash |
| **PC load**, stream on, dashboard closed | | |
| SteamVR/Steam processes CPU | 1.7% | 1.24% |
| Video encoder | NVENC, 12%, 183 fps | Vulkan Video, 30% (no session/fps reported) |
| Standalone receiving, SteamVR closed | 0% SteamVR CPU, encoder idle | 0.14% Steam CPU, encoder idle |

Findings:

- **Frame's tracking does not depend on the PC's OS.** Its own tracking rate
  (standalone, about 231-233 Hz; 175 Hz at a 200 Hz send rate) was the same
  in both runs.
- **On Ubuntu, home Wi‑Fi limits both modes.** Standalone stalled in every
  run instead of 2 of 6, and streaming lost 9-14% of real tracking samples
  and dropped repeatedly: without the direct link, the combined stream has
  only home Wi‑Fi left. On Windows the direct link carried it alongside
  Wi‑Fi.
- **Streaming latency is not comparable yet.** The Ubuntu values range from
  1 to 23 ms with weak trace matches; the Windows rate pattern (17 ms, 3 ms at
  unlimited) did not reappear. Standalone was never later than streaming on
  either OS.
- **Linux encodes the stream with more effort** (Vulkan Video, about 30%
  encoder against 12% NVENC); CPU cost is similar and small on both.
- **Next:** rerun the Ubuntu benchmark over the direct link once a 7.2+
  kernel lets the adapter join; that run isolates the operating system.

## Tests

```powershell
python -B -m unittest discover -s general/tests -v
```

Covers loopback UDP, sender/receiver interoperability, FVR1/FVR2 packets,
malformed input, sequence/session handling, relative pose maths, config
validation, the OpenVR sampler against a fake runtime, viewer previews, and the
measurement tools' analysis. Run them with UDP port 9000 free.

## Dependencies and attribution

Bundled pyopenvr source and Valve's ARM64 OpenVR library retain their upstream
licenses; see [non_pc_streaming/vendor/PROVENANCE.md](non_pc_streaming/vendor/PROVENANCE.md).

Official Frame documentation:
- https://partner.steamgames.com/doc/steamhardware/steamframe/setup
- https://partner.steamgames.com/doc/steamhardware/steamframe/engines/custom
- https://partner.steamgames.com/doc/steamhardware/steamframe/debugging
