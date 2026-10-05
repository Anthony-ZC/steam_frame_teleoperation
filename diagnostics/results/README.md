# Benchmark results

Raw output of the measurement tools behind the tables in [Benchmarks](../README.md#benchmarks). Measured on the test PC described
there: Windows 2026-10-04 (folders below), Ubuntu 2026-10-05 (`ubuntu_wifi/`).
One folder per table; file names are `<mode>_<path>_<send rate>.json` (`direct` = Frame's direct link, `wifi` =
home Wi‑Fi). Discarded and repeat runs are not included. The files contain no
network addresses.

| Folder | Benchmark table | Tool | Files |
|---|---|---|---|
| `pc_load/` | [PC load and pose stability](../README.md#pc-load-and-pose-stability) | `measure_stream_load` (+ `measure_udp_rate` for the standalone pose rows: `*_packets.json`) | `stream_off`, `stream_on_dashboard_open`, `stream_on_dashboard_closed`, `standalone_direct_200hz` |
| `data_rate/` | [Data rate and timing](../README.md#data-rate-and-timing-streaming-vs-standalone) | `measure_udp_rate` | `streaming_*`, `standalone_direct_*`, `standalone_wifi_*` at 100 Hz, 200 Hz, unlimited |
| `latency_absolute/` | [Absolute latency](../README.md#absolute-latency) | `measure_udp_rate --sync` (`standalone_*`), `measure_latency --sync` (`streaming_and_standalone_*`) | per path and rate |
| `latency_relative/` | [Relative latency](../README.md#relative-latency) | `measure_latency` | `standalone_vs_streaming_*` |

`ubuntu_wifi/` holds the same four folders for the Ubuntu run (2026-10-05,
home Wi‑Fi only; [Ubuntu, home Wi‑Fi](../README.md#ubuntu-home-wifi)):
`streaming_*` there means the stream over home Wi‑Fi, every `standalone_*`
file is `standalone_wifi_*`, and `pc_load/` has no direct-link run. Load
files from Linux have no `gpu` engine split; use `nvidia.gpu_util` and
`nvidia.encoder_util`.

Key fields:

- `measure_udp_rate`: `rate_hz`, `lost`, `arrival_ms` (packet interval),
  `delay_jitter_ms` (delay variation), per controller `tracking_update_hz`
  (real tracking samples) and `tracking_interval_ms`; with sync also
  `latency_ms`, `new_sample_latency_ms` and `sync` (offset, round trip, error
  bound, drift).
- `measure_latency`: per controller `standalone_minus_streaming_ms` and
  `correlation`; with sync also `streaming_latency_ms`,
  `standalone_latency_ms` and `sync`.
- `measure_stream_load`: `cpu_total`, `gpu`, `vr_processes_cpu_total`,
  `nvidia` (GPU, encoder use and fps), `pose` (pose change rate and intervals).

All times are in milliseconds, rates in Hz.
