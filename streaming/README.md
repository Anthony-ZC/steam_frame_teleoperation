# PC streaming mode

Reads controller data from **PC SteamVR** while Frame streams to the PC.
Start SteamVR and the stream (a minimized desktop is enough), **close the
SteamVR dashboard** in the headset (it otherwise takes all button and finger
input), and keep the controllers awake and in view.

| File | Purpose |
|---|---|
| `frame_pose.py` | `SteamVRReader`: starts OpenVR on the PC; a thin wrapper around the shared `general/openvr_sampler.py` (also used by the Frame sender) |
| `read_poses.py` | prints poses and inputs, optionally logs CSV |
| `requirements.txt` | `openvr` (pyopenvr) |

From the repository root:

```powershell
python -m general.visualize_poses
python -m streaming.read_poses
python -m streaming.read_poses --csv artifacts/poses.csv --seconds 30
python -m streaming.read_poses --demo --seconds 2
```

`read_poses` prints twice per second, polls at 100 Hz by default, applies the
relative pose from `config.toml`, and accepts `--hz`, `--csv`, `--seconds` and
`--config`. CSV columns follow `[fields]`; `pose_frame` says whether a row is
absolute (during the settle countdown) or relative.

With the stream off, SteamVR still reports the controllers as tracked but the
poses freeze. Probes and measurements live in
[diagnostics/](../diagnostics/README.md); measured load and stability are in the
root README [Benchmarks](../README.md#benchmarks).
