# Steam Frame pose visualization and teleoperation prototype

Read and visualize Steam Frame controller poses with Python. This project
provides a PC SteamVR reader and an experimental sender that runs locally on
Frame and forwards poses over UDP, avoiding PC video streaming.

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
streaming/                 PC streaming / SteamVR
  frame_pose.py            OpenVR pose reader
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
  poses.py                 Pose model and synthetic reader
  pose_wire.py             UDP packet format
  visualize_poses.py        Shared viewer
  requirements.txt         PC visualization dependencies
  tests/                   Network/protocol tests
artifacts/                 Generated previews/packages; ignored by Git
```

The small `__init__.py` files make each source folder a Python package.

## PC SteamVR mode

Connect Frame to PC SteamVR using its streaming connection. Keep the headset
awake and the controllers visible to its tracking cameras.

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses
```

The viewer targets 90 Hz and uses partial redraws to avoid redrawing the static
3D grid every frame. Drag to rotate the camera. `--hz 120` changes the requested
refresh rate, `--span 4` increases view width, and `--full-redraw` disables the
fast rendering path. Actual display rate depends on the graphics backend.

Try synthetic trajectories without hardware:

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses --demo
.\.venv\Scripts\python.exe -m general.visualize_poses --demo --benchmark 120
```

Print poses, log CSV, or check tracking through the streaming utilities:

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
Mode enabled, a user password, Python 3.9+, an active local VR runtime, and an
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
handling. Run them with UDP port 9000 free.

Changed pose values do not
measure the underlying sensor's sample rate or end-to-end latency.

## Dependencies and attribution

Bundled pyopenvr source and Valve's ARM64 OpenVR library retain their upstream
licenses. See [non_pc_streaming/vendor/PROVENANCE.md](non_pc_streaming/vendor/PROVENANCE.md).

Official Frame documentation:
- https://partner.steamgames.com/doc/steamhardware/steamframe/setup
- https://partner.steamgames.com/doc/steamhardware/steamframe/engines/custom
- https://partner.steamgames.com/doc/steamhardware/steamframe/debugging
