# Pending benchmark: fair streaming vs. standalone comparison

Status: **done** (run 2026-10-04). Results: root README
[Fair comparison](../README.md#fair-comparison-streaming-vs-standalone).
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
