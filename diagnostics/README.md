# Diagnostics

Probes and measurements for investigating hardware, runtime and performance.
Nothing in `general/`, `streaming/` or `non_pc_streaming/` imports these tools.
Run them from the repository root. Results are summarized in the root README
[Benchmarks](../README.md#benchmarks), with the raw results behind its tables in
[results/](results/README.md); the procedure for reruns is in
[benchmark_plan.md](benchmark_plan.md).

| Tool | Runs on | What it answers |
|---|---|---|
| `probe_controller.py` | PC or Frame (numpy-free) | Which OpenVR runtime is found, which controllers exist, which data groups arrive and change; warns when the dashboard takes the input |
| `measure_stream_load.py` | PC (Windows, Linux) | CPU/GPU/encoder cost of a setup and pose stability under it; `--compare` several runs |
| `measure_udp_rate.py` | PC (receiver) | UDP rate, loss, reordering, arrival/send intervals, delay jitter, new-pose rate, true tracking rate (velocity changes); absolute and new-sample latency with `--sync` (or a sender on this PC) |
| `measure_latency.py` | PC | Relative latency standalone vs. streaming: both pipelines at once, cross-correlated speed traces; with `--sync` absolute latency of both modes from the Frame pose read |
| `measure_pose_rate.py` | PC | How often PC SteamVR returns a changed pose, and the interval spread |
| `diagnose_tracking.py` | PC | Whether poses differ as background app vs. scene app (`scene` takes VR focus) |
| `run_ubuntu_wifi_benchmark.sh` | PC (Ubuntu) | Guided rerun of all benchmarks over home Wi‑Fi; see [benchmark_plan.md](benchmark_plan.md#ubuntu-home-wifi-only) |

```powershell
python -m diagnostics.probe_controller --seconds 20          # --quiet: summary only
python -m diagnostics.measure_stream_load --label minimized --seconds 60
python -m diagnostics.measure_stream_load --compare artifacts/stream_load_*.json
python -m diagnostics.measure_udp_rate --sender-ip FRAME_IP --seconds 30 --label wifi
python -m diagnostics.measure_latency --sender-ip FRAME_IP --seconds 20 --label run1
python -m diagnostics.measure_udp_rate --sender-ip FRAME_IP --sync --label abs     # sender needs --sync
python -m diagnostics.measure_pose_rate
python -m diagnostics.diagnose_tracking background
```

Notes:

- `measure_udp_rate` and `measure_latency` listen on UDP 9000: close the viewer
  first. They wait (`--wait`, default 120/300 s) for the first packet, so start
  them before the sender. Rejected packets are listed by source and session; an
  "other session" means a second sender is still running on Frame.
- Runtimes extrapolate poses, so changed positions overstate the tracking
  rate; the velocity only changes with a real tracking sample.
- On Frame, `non_pc_streaming/deploy_sender.ps1 -Probe` uploads and runs the
  probe. Saved runs go to `artifacts/<tool>_<label>.json` (ignored by Git);
  copy the ones a README table cites into `results/` with a descriptive name.
