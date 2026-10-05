# Pending benchmark: fair streaming vs. standalone comparison

Status: **done** (run 2026-10-04). Results: root README
[Data rate and timing](../README.md#data-rate-and-timing-streaming-vs-standalone),
raw data in [results/data_rate/](results/data_rate/).
Outcome of the open risks: 1b worked (Frame's local runtime and the PC stream
ran together); velocity changes did reveal the real tracking rate (about
217 Hz streaming, about 233 Hz standalone). Keep this file as the procedure
for reruns on other hardware.

## Goal

Compare PC streaming and standalone mode with the same metrics, at 100 Hz,
200 Hz and the unlimited (natural) rate:

- data frequency as delivered, and the **true tracking rate**;
- latency: absolute on loopback, and **relative latency standalone vs. streaming**.

## Why the earlier numbers are not comparable

- Streaming was measured by local polling (`measure_stream_load`); standalone by
  UDP arrival (`measure_udp_rate`).
- Both runtimes extrapolate poses, so a changed position does not prove a new
  tracking sample. Velocity only changes with a real sample, so
  `measure_udp_rate` now reports "tracking updates (velocity changes)".

## Tools

| Tool | Role |
|---|---|
| `non_pc_streaming/frame_sender.py --hz 0` | unlimited send rate (also `deploy_sender.ps1 -Hz 0`) |
| `non_pc_streaming/frame_sender.py --desktop` | standalone sender running on the PC against PC SteamVR (streaming mode, same packets) |
| `diagnostics/measure_udp_rate.py` | rate, loss, intervals, tracking updates; absolute latency when the sender is on this PC |
| `diagnostics/measure_latency.py` | runs both pipelines at once, cross-correlates the controllers' speed traces on the PC clock: ms by which standalone lags streaming |

## Procedure

Both controllers on, viewer closed (UDP port 9000), every `[fields]` group.
Move the controllers briskly during latency runs (swing, stop, repeat).

### Phase 1: stream on, SteamVR dashboard closed

1a. Streaming frequency (run on the PC, no password needed), 30 s each:

```powershell
python -m diagnostics.measure_udp_rate --sender-ip 127.0.0.1 --seconds 30 --label streaming_100hz
python -m non_pc_streaming.frame_sender --desktop --pc 127.0.0.1 --hz 100 --seconds 40
```

Repeat with `--hz 200` (`streaming_200hz`) and `--hz 0` (`streaming_unlimited`).

1b. Relative latency, Frame sender over the direct link, 20 s each:

```powershell
python -m diagnostics.measure_latency --sender-ip FRAME_WLANAP_IP --seconds 20 --label latency_100hz
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_WLANAP_IP -PcAddress PC_DIRECT_IP -Hz 100
```

Repeat with `-Hz 200` (`latency_200hz`) and `-Hz 0` (`latency_unlimited`).

### Phase 2: stream off, PC SteamVR closed

Standalone unlimited rate over the direct link (100/200 Hz already measured;
remeasure them too if the true tracking rate is wanted for those):

```powershell
python -m diagnostics.measure_udp_rate --sender-ip FRAME_WLANAP_IP --seconds 30 --label wlanap_unlimited
.\non_pc_streaming\deploy_sender.ps1 -FrameHost FRAME_WLANAP_IP -PcAddress PC_DIRECT_IP -Hz 0
```

## Absolute latency (clock sync)

Status: **done** (run 2026-10-04). Results: root README
[Absolute latency](../README.md#absolute-latency), raw data in
[results/latency_absolute/](results/latency_absolute/). Open: why
streaming lags about 17 ms with the Frame sender at 100/200 Hz but only about
3-5 ms at the unlimited rate (reproduced twice each).

Tools: `general/clock_sync.py`, sender `--sync`,
`measure_udp_rate --sync`, `measure_latency --sync`. Deploy once with `-Sync`
(new file), later run the sender directly over SSH with `--sync`. One listener
at a time; start it before the sender.

Phase A, stream off, PC SteamVR closed (standalone absolute + new-sample
latency), for each path (direct link, home Wi‑Fi) and rate (100, 200, 0):

```powershell
python -m diagnostics.measure_udp_rate --sender-ip FRAME_IP --sync --seconds 30 --label abs_<path>_<rate>
ssh -t steamos@FRAME_IP "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_IP --hz <rate> --sync"
```

Phase B, stream on, dashboard closed (streaming absolute latency), Frame sender
over the direct link at 100, 200, 0 Hz; move the controllers briskly:

```powershell
python -m diagnostics.measure_latency --sender-ip FRAME_WLANAP_IP --sync --seconds 20 --label abs_<rate>
ssh -t steamos@FRAME_WLANAP_IP "cd ~/frame_pose_sender && python3 -m non_pc_streaming.frame_sender --pc PC_DIRECT_IP --hz <rate> --sync"
```

Check every result's sync line: error bound (expected about ±0.5 ms direct,
±1.5 ms home Wi‑Fi) and "no replies" (sender started without `--sync`, or
Frame blocks inbound UDP 9001).

## Open risks and caveats

- 1b needs Frame's local runtime and the PC stream at the same time; untested.
- In 1b the standalone packets share the direct link with the video stream, so
  they see more jitter than in pure standalone use.
- If a runtime also extrapolates velocity, "tracking updates" will equal the
  poll rate; report it as "not detectable" then.
- Relative latency is not motion-to-data latency; that still needs an external
  reference (e.g. high-speed video of the controller and the viewer).
- Stop every sender window between runs (`pgrep`/`pkill` commands in the root
  README); a leftover sender shows up as "other session" rejections.

## Ubuntu, home Wi‑Fi only

Status: **done** (run 2026-10-05). Results: root README
[Ubuntu, home Wi‑Fi](../README.md#ubuntu-home-wifi) and
[Windows vs. Ubuntu](../README.md#windows-vs-ubuntu), raw data in
[results/ubuntu_wifi/](results/ubuntu_wifi/). The run was driven by hand with
the same commands; check the vrlink log (`Connection inactive`) after every
streaming run, the Wi‑Fi stream dropped several times. Same PC, Ubuntu 26.04 (kernel 7.0). The Frame wireless
adapter needs kernel 7.2+, so there is no direct link: the PC stream and the
standalone sender both use home Wi‑Fi. Compared with the Windows run, the
streaming rows therefore change path (Wi‑Fi only instead of Valve's combined
direct link + Wi‑Fi streaming) and the standalone direct-link rows are dropped.

`diagnostics/run_ubuntu_wifi_benchmark.sh FRAME_WLAN0_IP PC_IP` runs the whole
matrix with a pause before every setup change, labels `ubuntu_wifi_*`:

| Phase | Setup | Runs |
|---|---|---|
| `deploy`, `ping` | – | upload the sender; 40-sample round trip |
| `load` | SteamVR on: stream off / dashboard open / dashboard closed | `measure_stream_load`, 20 s each |
| `streaming` | stream on over Wi‑Fi, dashboard closed | data rate on loopback (`--desktop`), `measure_latency --sync`, `measure_latency`; 100, 200, 0 Hz |
| `standalone` | stream off, PC SteamVR quit | `measure_udp_rate`, `measure_udp_rate --sync`, load at 200 Hz; 100, 200, 0 Hz |

Phases can be run alone (`... FRAME_IP PC_IP streaming`). Before the first
run, accept Frame's host key once (`ssh steamos@FRAME_WLAN0_IP true`); the
script uses non-interactive SSH. Linux differences: the load tool reads
`/proc` (no per-engine GPU split; use the NVIDIA rows), and SteamVR encodes
with Vulkan Video, so `nvidia-smi` shows encoder utilization but 0 NVENC
sessions and fps.
