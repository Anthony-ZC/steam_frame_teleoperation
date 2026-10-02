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

`read_poses` prints twice per second, polls at 30 Hz by default, and accepts
`--hz`, `--csv`, and `--seconds`. `diagnose_tracking scene` temporarily takes
VR scene focus to compare the compositor pose path. The rate utility measures
changes in returned poses, not hardware measurement timestamps.

The shared viewer, pose model, and demo reader live in `general/`.
