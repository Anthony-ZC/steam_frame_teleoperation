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

**Platforms:** everything was tested on Windows 11. On Ubuntu, the viewer, UDP
receiver, logger, tests and UDP/latency measurement tools are plain Python and
should work unchanged; PC streaming mode needs SteamVR for Linux (untested).
Windows-only parts: `non_pc_streaming/deploy_sender.ps1` (manual Linux commands
in [non_pc_streaming/README.md](non_pc_streaming/README.md#on-ubuntu-without-the-script)),
the Windows Firewall commands (Ubuntu: `ufw`, below) and
`diagnostics/measure_stream_load.py` (Windows performance counters).

## Folder structure

```text
config.toml                Field selection, relative pose mode, OpenVR app type
general/                   Shared by both modes
  visualize_poses.py       Viewer: 3D relative pose + hand/controller panels
  openvr_sampler.py        OpenVR sampling, used on the PC and on Frame (numpy-free)
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
  measure_latency.py       Relative latency standalone vs. streaming
  measure_pose_rate.py     Pose-change frequency from PC SteamVR
  diagnose_tracking.py     Background vs. scene app tracking
  benchmark_plan.md        Planned fair comparison (not run yet)
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
| `wlanap` | Frame's own access point: the **direct link** used for PC streaming | the PC adapter on the same subnet, with **no** default gateway (e.g. `Wi-Fi 6`) |
| `usb0` | networking over a USB cable, if connected | – |

Addresses from DHCP can change; check again if a connection stops working.

### Home Wi‑Fi or direct link?

| | Home Wi‑Fi (`wlan0`) | Direct link (`wlanap`) |
|---|---|---|
| Path | Frame → router → PC | Frame → PC, no router |
| Round trip (ping) | about 4 ms avg, up to 18 ms | about 1 ms avg, up to 5 ms |
| Delay variation (p99) | 4-6 ms in good runs, **130+ ms** in bad ones | about 3 ms in every run |
| Worst stall | up to about 190 ms (in 4 of 7 runs) | about 20-40 ms |
| Needs | both devices on the same router | the PC's streaming adapter connected to Frame (stayed up with PC SteamVR closed) |

**Use the direct link** when it is available. Both deliver every packet and
the same tracking rate; details in the
[benchmarks](#fair-comparison-streaming-vs-standalone).

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
RTX 5090 (32 GB, driver 617.14), Windows 11 Pro 10.0.26200, SteamVR build
1789498647. Measured 2026-10-04 with the tools in [diagnostics/](diagnostics/README.md);
raw results in `artifacts/*.json`.

### PC load and pose stability

`diagnostics.measure_stream_load`, 20 s per streaming run (desktop stream, both
controllers, pose-only polling from a background OpenVR app). The standalone
column is the Frame sender over the direct link at 200 Hz, PC SteamVR closed,
30 s; its pose rows are UDP arrival (see [Fair comparison](#fair-comparison-streaming-vs-standalone)).

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
  [fair comparison](#fair-comparison-streaming-vs-standalone). With the stream
  off, poses froze while still reported as tracked.

### Fair comparison: streaming vs. standalone

Same tool (`measure_udp_rate`), same packets, both controllers moving, every
`[fields]` group, 30 s per run, dashboard closed. "Tracking updates" count
velocity changes, which only occur with a real tracking sample (positions are
extrapolated between samples).

- **Streaming**: PC SteamVR with the Frame stream; sender on the PC
  (`frame_sender --desktop`) over loopback. The Frame-to-PC part travels
  inside SteamVR's link and is not visible.
- **Standalone, direct link**: sender on Frame, from its `wlanap` access point
  to the PC's direct-link adapter (`Wi-Fi 6`); stream off, PC SteamVR closed.
- **Standalone, home Wi‑Fi**: sender on Frame, from `wlan0` via the router to
  the PC's home Wi‑Fi adapter; stream off, PC SteamVR closed.

| Mode | Send rate | Delivered | Tracking updates (real samples) | Tracking interval median / p95 | Arrival interval median / p99 / max | Loss | Delay variation median / p99 / max |
|---|---|---|---|---|---|---|---|
| Streaming | 100 Hz | 100 Hz | 100 Hz | 10.0 / 10.3 ms | 10.0 / 10.5 / 10.6 ms | 0 | 0.04 / 0.15 / 0.28 ms (loopback) |
| Streaming | 200 Hz | 200 Hz | 168-171 Hz | 5.1 / 10.1 ms | 5.0 / 5.6 / 5.9 ms | 0 | 0.04 / 0.13 / 0.25 ms (loopback) |
| Streaming | unlimited | 4525 Hz | **≈ 217 Hz** | 4.5 / 8.5 ms | 0.2 / 0.4 / 38.5 ms | 0 | 0.01 / 0.14 / 38.3 ms (loopback) |
| Standalone, direct link | 100 Hz | 100 Hz | 99.8-99.9 Hz | 10.0 / 11.5 ms | 10.0 / 12.7 / 32.9 ms | 0 | 0.57 / 3.3 / 22.8 ms |
| Standalone, direct link | 200 Hz | 200 Hz | 174-175 Hz | 5.1 / 10.3 ms | 5.0 / 7.2 / 40.7 ms | 0 | 0.53 / 2.9 / 36.7 ms |
| Standalone, direct link | unlimited | 2464 Hz | **≈ 233 Hz** | 4.1 / 8.1 ms | 0.03 / 2.1 / 20.1 ms (batched) | 3 of 73,886 | 1.29 / 3.4 / 31.4 ms |
| Standalone, home Wi‑Fi | 100 Hz | 100 Hz | 99.7-99.8 Hz | 10.0 / 11.5 ms | 10.0 / 55.6 / **185.7** ms | 0 | 1.20 / **134.0 / 177.5** ms |
| Standalone, home Wi‑Fi | 200 Hz | 200 Hz | 174-177 Hz | 5.1 / 10.2 ms | 5.0 / 7.4 / 26.6 ms | 0 | 1.47 / 3.8 / 22.9 ms |
| Standalone, home Wi‑Fi | unlimited | 2523 Hz | **≈ 233 Hz** | 4.1 / 8.3 ms | 0.03 / 3.0 / 23.7 ms (batched) | 0 | 2.03 / 6.1 / 26.3 ms |

Network round trip PC ↔ Frame (`ping`, 40 samples, min / avg / max): direct
link 1 / 1 / 5 ms, home Wi‑Fi 3 / 4 / 18 ms.

**Relative latency** (`measure_latency`). There is no absolute clock for "the
hand moved", so latency is measured as a *difference*: streaming and standalone
run at the same time on the same hand motion, both timestamped on arrival at
the PC, and the controllers' speed traces are cross-correlated. Streaming is the
fixed reference (PC SteamVR read directly at its natural rate, polled at about
930 Hz); only the standalone side varies. Each cell is how much later (+) or
earlier (−) standalone arrives than streaming. The stream was on during these
runs, so the standalone packets shared the direct link with the video
(conservative for standalone).

| Standalone path | Standalone send rate | Reference | Left | Right | Correlation (left / right) |
|---|---|---|---|---|---|
| Direct link | 100 Hz | Streaming, natural rate | −15.2 ms | −1.9 ms | 0.99 / 0.98 |
| Direct link | 200 Hz | Streaming, natural rate | +2.6 ms | −15.1 ms | 0.97 / 0.99 |
| Direct link | unlimited (about 2900 Hz) | Streaming, natural rate | −1.9 ms | −7.4 ms | 1.00 / 0.98 |
| Home Wi‑Fi | any | – | not measured | not measured | – |

Streaming throttled to 100 or 200 Hz was not used as a reference; throttling a
side adds on average half a send interval (5 ms at 100 Hz, 2.5 ms at 200 Hz)
plus any repeated samples.

Findings:

- **Natural tracking rate**: about 217 Hz through PC streaming, about 233 Hz
  from Frame's local runtime (one real sample every 4-4.5 ms).
- **100 Hz** gives a real sample in practically every packet in both modes.
  **200 Hz** is close to the natural rate, so the two clocks drift against each
  other and 13-16% of packets repeat the previous sample. To get every sample,
  send faster than the natural rate (unlimited); to get regular packets, stay
  well below it.
- **Latency: standalone is at least as fast as streaming.** All six
  measurements lie between 15.2 ms earlier and 2.6 ms later (mean about
  6.5 ms earlier). The per-controller offset changes between runs by about
  15 ms, independent of the rate, so it looks like a sampling-phase effect
  between the two runtimes rather than a property of either mode.
- Standalone pays for its network hop with jitter (direct link: delay
  variation p99 about 3 ms, rare spikes of 20-40 ms); in streaming that part
  is hidden inside SteamVR and not measurable here.
- **Home Wi‑Fi is unpredictable.** The tracking rate is the same as over the
  direct link (it comes from Frame), and two of the three runs were nearly as
  clean, but with a higher baseline (delay variation median 1.5-2 ms vs.
  0.5-1.3 ms). The 100 Hz run had stalls up to 186 ms (p99 134 ms); counting
  every home Wi‑Fi run on 2026-10-04 (90-200 Hz and unlimited), 4 of 7 showed
  such 150-190 ms bursts, independent of the rate. The direct link never did.
  **Use the direct link**; on home Wi‑Fi, a robot controller must tolerate
  such stalls.
- At unlimited rate Wi‑Fi delivers packets in batches (median arrival interval
  0.03 ms), so "gaps > 3x median" is not meaningful there; the streaming
  unlimited run had one 38 ms stall on the PC.

### Latency

| What | Result |
|---|---|
| Network round trip PC ↔ Frame (`ping`, 40 samples) | home Wi‑Fi 3 / 4 / 18 ms, direct link 1 / 1 / 5 ms (min / avg / max) |
| One-way delay *variation* | in the fair comparison table above |
| Absolute one-way packet latency | not measured (PC and Frame clocks are not synchronized) |
| Loopback latency, sender on the PC (same clock) | 0.06-0.12 ms median |
| Relative latency standalone vs. streaming | standalone 15.2 ms earlier to 2.6 ms later, mean about 6.5 ms earlier ([fair comparison](#fair-comparison-streaming-vs-standalone)) |
| Motion-to-data latency | not measured; needs an external reference such as high-speed video |

### Method notes

- The first table's streaming pose rows come from local polling, the
  standalone data-flow rows from UDP arrival; only the
  [fair comparison](#fair-comparison-streaming-vs-standalone) uses the same
  method for both modes. The procedure is in
  [diagnostics/benchmark_plan.md](diagnostics/benchmark_plan.md).
- Both runtimes extrapolate poses: a changed position is not proof of a new
  tracking sample; velocity changes are.
- One run per configuration on one PC and one network; rerun on other
  hardware before generalizing. Discarded runs (a leftover sender measured, or
  no tracked controllers) are kept in `artifacts/` with `INVALID` in the name.

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
