# PC streaming mode

This folder contains code that reads poses from **PC SteamVR**. Frame needs an
active PC streaming connection and tracking must remain awake.

Run from the repository root with the project's virtual environment:

```powershell
.\.venv\Scripts\python.exe -m general.visualize_poses
.\.venv\Scripts\python.exe -m streaming.read_poses
.\.venv\Scripts\python.exe -m streaming.read_poses --demo --seconds 2
.\.venv\Scripts\python.exe -m streaming.diagnose_tracking background
.\.venv\Scripts\python.exe -m streaming.measure_pose_rate
```

`read_poses` prints poses and inputs twice per second, polls at 100 Hz by
default, applies the relative pose from `config.toml`, and accepts `--hz`,
`--csv`, `--seconds` and `--config`. `diagnose_tracking scene` temporarily takes
VR scene focus to compare the compositor pose path. The rate utility measures
changes in returned poses, not hardware measurement timestamps.

`SteamVRReader` in `frame_pose.py` is a thin wrapper around the shared
`general/openvr_sampler.py`, which the Frame sender also uses. The viewer,
controller probe, pose model, config and demo reader live in `general/`.
