# Shared code: viewer, sampler, packet format, config

Used by both modes. Modules marked numpy-free also run on Frame.

| File | Purpose |
|---|---|
| `visualize_poses.py` | Viewer: 3D relative pose + hand/controller panels |
| `openvr_sampler.py` | OpenVR sampling, used on the PC and on Frame (numpy-free) |
| `clock_sync.py` | Optional Frame/PC clock sync for absolute latency (numpy-free) |
| `controller_state.py` | `ControllerState`: pose, velocity, buttons, fingers (numpy-free) |
| `pose_wire.py` | UDP packet formats FVR1 (poses) and FVR2 (+ optional groups) |
| `relative_pose.py` | Relative pose after a settle delay, reset |
| `readers.py`, `demo.py` | Reader base class, demo reader, synthetic states |
| `poses.py`, `config.py` | Pose model (numpy), `config.toml` loader |
| `input/` | SteamVR Input action manifest + bindings (`make_manifest.py`) |
| `tests/` | Unit and loopback tests |

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

While the SteamVR dashboard is open (for example showing the streamed
desktop) it receives all controller input, and every other app's buttons,
analog values and fingers go inactive; poses still arrive. The viewer, probe
and sender say when this happens.

The legacy controller state returns nothing for a background app, so SteamVR
Input (`input/actions.json`) is the working path. Bindings ship for
`frame_controller` and `knuckles`; regenerate them with
`python -m general.input.make_manifest`.

## Viewer

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
- On Ubuntu it needs a matplotlib GUI backend in the venv (`pip install
  PyQt6`, or `sudo apt install python3-tk`), otherwise it exits with
  "FigureCanvasAgg is non-interactive".

## Tests

```powershell
python -B -m unittest discover -s general/tests -v
```

Covers loopback UDP, sender/receiver interoperability, FVR1/FVR2 packets,
malformed input, sequence/session handling, relative pose maths, config
validation, the OpenVR sampler against a fake runtime, viewer previews, and the
measurement tools' analysis. Run them with UDP port 9000 free.
