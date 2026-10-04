# Steam Frame pose visualization and teleoperation prototype

Read and visualize Steam Frame controller poses, buttons, touch sensors and
finger curl with Python. This project provides a PC SteamVR reader and an
experimental sender that runs locally on Frame and forwards poses over UDP,
avoiding PC video streaming.

The scripts collect and display poses only. They do not control a robot.

## Windows setup

Use 64-bit Python 3.11 or 3.12:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run all commands from the repository root, using `python -m` so imports work
across folders. For UDP/demo visualization only, install
`general/requirements.txt`; the headset sender uses the standard library and
the bundled dependencies, without NumPy or Matplotlib.

## Folder structure

```text
config.toml                Field selection, relative pose mode, OpenVR app type
streaming/                 PC streaming / SteamVR
  frame_pose.py            SteamVRReader (OpenVR on the PC)
  read_poses.py            Console output and CSV logging
  diagnose_tracking.py     Tracking diagnostics
  measure_pose_rate.py     Observed pose-change frequency
  requirements.txt         OpenVR dependency
non_pc_streaming/          Experimental operation without PC video streaming
  frame_sender.py          Sender running on Frame
  udp_pose.py              Receiver running on PC
  deploy_sender.ps1        Upload and launch
  vendor/                  Bundled headset dependencies and licenses
  README.md                Standalone setup and limitations
general/                   Shared by both modes
  config.py                config.toml loader (stdlib only)
  controller_state.py      ControllerState: pose, velocity, buttons, fingers (numpy-free)
  openvr_sampler.py        OpenVR sampling used on the PC and on Frame (numpy-free)
  probe_controller.py      Lists what each controller exposes (PC or Frame)
  input/                   SteamVR Input action manifest + bindings (make_manifest.py)
  readers.py               ControllerReader base class and DemoReader
  poses.py                 Pose model (numpy)
  relative_pose.py         Relative pose after a settle delay, reset
  pose_wire.py             UDP packet format
  visualize_poses.py       Shared viewer
  requirements.txt         PC visualization dependencies
  tests/                   Network/protocol, relative pose, sampler tests
artifacts/                 Generated previews/packages; ignored by Git
```

The small `__init__.py` files make each source folder a Python package.

## PC SteamVR mode

Connect Frame to PC SteamVR using its streaming connection. Keep the headset
awake and the controllers visible to its tracking cameras.

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses
```

The 3D view shows each controller's pose **relative** to a reference captured
`settle_seconds` (default 3 s) after launch; hold the controllers still during
the countdown. **Reset Pose** (or the `R` key) recaptures the reference from the
current poses. A controller that first appears later is referenced on first
sight, and keeps its reference through tracking loss.

Next to it, one panel per hand shows the hand and the controller together:
five finger-curl bars (thumb to pinky; shade = splay) and a controller sketch
with bumper, menu/view, system, thumbrest, trigger and grip (with analog fill),
thumbstick position, and the A/B/X/Y face buttons (the left controller's
mirrored d-pad). Lamps are grey when idle, outlined when **touched**, filled when
**pressed**, dotted when there is no data. Text lists the relative position,
roll/pitch/yaw, speed, battery, tracking and input source.

The viewer targets 90 Hz and uses partial redraws to avoid redrawing the static
3D grid every frame. Drag to rotate the camera. `--hz 120` changes the requested
refresh rate, `--span 4` increases view width, and `--full-redraw` disables the
fast rendering path. Actual display rate depends on the graphics backend.

### Configuration

`config.toml` (or `--config PATH`) controls both the viewer and the logger:

- `[fields]` turns data groups on or off: `velocity`, `battery`, `buttons`,
  `analog`, `fingers`. The pose is always included. With `buttons`, `analog`
  and `fingers` all off, SteamVR Input is never initialized.
- `[relative_pose]`: `enabled`, `mode` (`own_frame`: `T0^-1 * T`, motion in the
  controller's initial frame; `world_axes`: `p - p0` and `R * R0^T` along
  SteamVR standing axes), `settle_seconds`.
- `[input]`: `app_type` (`background`, `overlay`, `scene`) and `legacy_fallback`.

### What the controllers expose

Run the probe and touch, press and squeeze every control while it runs:

```powershell
.\.venv\Scripts\python.exe -m general.probe_controller --seconds 20
```

It prints device properties, live changes, and a per-group summary. Verified
on a Frame right controller over PC streaming (`frame_controller`, background
app):

| Group | Data | Source |
|---|---|---|
| pose | 3x4 transform, tracking result | IVRSystem |
| velocity | linear and angular velocity | IVRSystem |
| battery | battery level, charging, controller type | device properties |
| buttons | A/B/X/Y, menu/view, bumper, thumbstick, trigger, grip: click + touch; thumbrest and system: touch (system click is reserved by SteamVR) | SteamVR Input |
| analog | trigger, grip, thumbstick x/y | SteamVR Input |
| fingers | curl x5, splay x4 (skeletal level: partial) | SteamVR Input skeleton |

The legacy controller state returned nothing for a background app, so
SteamVR Input (`general/input/actions.json`) is the working path. Bindings ship
for `frame_controller` and `knuckles`; regenerate them with
`python -m general.input.make_manifest`.

### Demo mode

Try synthetic trajectories and inputs without hardware:

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses --demo
.\.venv\Scripts\python.exe -m general.visualize_poses --demo --benchmark 120
```

Print poses and inputs, log CSV (columns follow `[fields]`; `pose_frame` says
whether a row is absolute or relative), or check tracking:

```powershell
.\.venv\Scripts\python.exe -m streaming.read_poses --csv artifacts/poses.csv
.\.venv\Scripts\python.exe -m streaming.diagnose_tracking background
.\.venv\Scripts\python.exe -m streaming.measure_pose_rate
```

Create `artifacts` before saving CSV files there.

## Experimental standalone Frame mode

The sender uses Frame's local Linux ARM64 OpenVR runtime and sends compact UDP
snapshots to the PC. The receiver works without PC SteamVR. **Local UDP tests
pass, but live operation on Frame has not yet been verified.**

Start the PC viewer:

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses --udp --sender-ip FRAME_WIFI_IP
```

Then deploy and run the sender in a second PowerShell window:

```powershell
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_WIFI_IP -PcAddress PC_LAN_IP
```

Replace the placeholders with actual IPv4 addresses. Frame needs Developer
Mode enabled, a user password, Python 3.11+, an active local VR runtime, and an
IP route to the PC. Enter the password only in your terminal. Keep Frame awake.
Add `-Demo` to test network transport independently of live tracking.

See [non_pc_streaming/README.md](non_pc_streaming/README.md) for deployment, firewall, coordinates,
packet format, and verification limits.

## Tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s general/tests -v
```

Tests exercise real loopback UDP, sender/receiver interoperability, matrix
ordering, tracking loss, timeouts, malformed packets, and sequence/session
handling; relative pose math, config validation, the OpenVR sampler against a
fake runtime, and viewer previews. Run them with UDP port 9000 free.

Changed pose values do not
measure the underlying sensor's sample rate or end-to-end latency.

## Dependencies and attribution

Bundled pyopenvr source and Valve's ARM64 OpenVR library retain their upstream
licenses. See [non_pc_streaming/vendor/PROVENANCE.md](non_pc_streaming/vendor/PROVENANCE.md).

Official Frame documentation:
- https://partner.steamgames.com/doc/steamhardware/steamframe/setup
- https://partner.steamgames.com/doc/steamhardware/steamframe/engines/custom
- https://partner.steamgames.com/doc/steamhardware/steamframe/debugging
