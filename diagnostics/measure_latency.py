"""Relative latency between streaming and standalone mode, same motion, same PC clock.

Runs both pipelines at once and compares them: poses from PC SteamVR (Frame
streaming, dashboard closed) and poses from the Frame sender over UDP. Both are
timestamped with this PC's clock on arrival. The two runtimes use different
coordinate origins, so the controllers' *speed* traces are cross-correlated;
the best-matching time shift is how much later standalone poses arrive than
streaming poses (negative = standalone earlier).

With --sync (sender started with --sync too) the Frame/PC clock offset is
measured during the run, so each standalone pose also gets its Frame read time
on the PC clock. That gives absolute values on one scale: standalone latency =
arrival - Frame read time, streaming latency = how far the streaming speed
trace lags the Frame-read-time trace. Both runtimes extrapolate to "now", so
these are effective latencies. Motion-to-data latency (camera exposure and
tracking inside the runtime) still needs an external reference.

Close the viewer (same UDP port), start the stream and the Frame sender, then
move the controllers briskly (swing, shake, stop, repeat) during the run:

  python -m diagnostics.measure_latency --sender-ip FRAME_IP --seconds 20
"""
import argparse
import json
import socket
import time
from collections import defaultdict
from pathlib import Path
import numpy as np
from general.clock_sync import DEFAULT_PORT, ClockSync
from general.pose_wire import MAX_PACKET, decode

ARTIFACTS = Path(__file__).resolve().parent.parent / 'artifacts'


def capture(sender_ip, port=9000, seconds=20.0, wait=300.0, sync_port=None):
    """Return {'streaming': {name: [(t, x, y, z)]}, 'standalone': {...}} on one perf_counter clock.

    With sync_port, also 'standalone_read' (same poses at their Frame read time,
    mapped to the PC clock) and 'sync' (clock sync quality).
    """
    from general.config import Config
    from streaming.frame_pose import SteamVRReader
    traces = {'streaming': defaultdict(list), 'standalone': defaultdict(list)}
    raw = defaultdict(list)  # name -> [(arrival_s, sender_ns, x, y, z)]
    sync = ClockSync(sender_ip, sync_port) if sync_port else None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(('0.0.0.0', port))
    except OSError as exc:
        sock.close()
        raise SystemExit(f'Cannot listen on UDP {port}: {exc}\nClose the viewer (--udp) first.')
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
    sock.setblocking(False)
    try:
        reader = SteamVRReader(Config(fields=frozenset()))  # pose only: the lightest local poll
    except Exception as exc:
        sock.close()
        raise SystemExit(f'PC SteamVR not available ({type(exc).__name__}: {exc}); start it and the stream.')
    session = end = None
    deadline = time.perf_counter() + wait
    try:
        while True:
            now = time.perf_counter()
            if (end and now >= end) or (not end and now >= deadline):
                break
            for name, pose in reader.read().items():
                traces['streaming'][name].append((time.perf_counter(), *pose.T[:3, 3]))
            while True:
                try:
                    payload, source = sock.recvfrom(MAX_PACKET + 1)
                except BlockingIOError:
                    break
                received = time.perf_counter()
                if source[0] != sender_ip:
                    continue
                try:
                    packet_session, _, sender_ns, _, states = decode(payload)
                except (ValueError, OverflowError):
                    continue
                if session is None:
                    session, end = packet_session, received + seconds
                    for trace in traces['streaming'].values():
                        trace.clear()  # keep only the window where both sources run
                    if sync:
                        sync.start(interval=2.0)
                if packet_session != session:
                    continue
                for s in states:
                    traces['standalone'][s.name].append((received, s.matrix[3], s.matrix[7], s.matrix[11]))
                    raw[s.name].append((received, sender_ns, s.matrix[3], s.matrix[7], s.matrix[11]))
            time.sleep(0.0005)
    finally:
        reader.close()
        sock.close()
        if sync:
            sync.stop()
            if session is not None:
                sync.burst()
            offset_fn, traces['sync'] = sync.offset_fn(), sync.quality()
            sync.close()
            if offset_fn:  # Frame read time on the PC clock: sender_ns - offset
                traces['standalone_read'] = {
                    name: [((ns - offset_fn(t * 1e9)) / 1e9, x, y, z) for t, ns, x, y, z in entries]
                    for name, entries in raw.items()}
            else:
                traces['sync'] = {'error': 'no replies (sender started without --sync, or UDP blocked)'}
    return traces


def speed_on_grid(samples, grid, smooth_s=0.02):
    """Interpolate positions onto a uniform grid, differentiate, smooth: speed in m/s."""
    data = np.asarray(samples, dtype=float)
    t, unique = np.unique(data[:, 0], return_index=True)
    positions = np.column_stack([np.interp(grid, t, data[unique, k]) for k in (1, 2, 3)])
    dt = grid[1] - grid[0]
    speed = np.linalg.norm(np.gradient(positions, dt, axis=0), axis=1)
    window = max(1, int(round(smooth_s / dt)))
    return np.convolve(speed, np.ones(window) / window, mode='same')


def best_lag(reference, delayed, dt, max_lag_s=0.25):
    """Shift (s) at which `delayed` best matches `reference`; positive = `delayed` lags. Returns (lag, corr)."""
    a = (reference - reference.mean()) / (reference.std() or 1.0)
    b = (delayed - delayed.mean()) / (delayed.std() or 1.0)
    max_k = int(max_lag_s / dt)
    lags = np.arange(-max_k, max_k + 1)
    corr = np.array([np.mean(a[max(0, -k):len(a) - max(0, k)] * b[max(0, k):len(b) - max(0, -k)])
                     for k in lags])
    i = int(np.argmax(corr))
    shift = float(lags[i])
    if 0 < i < len(corr) - 1:  # parabolic refinement between grid steps
        y0, y1, y2 = corr[i - 1], corr[i], corr[i + 1]
        denominator = y0 - 2 * y1 + y2
        if denominator:
            shift += 0.5 * (y0 - y2) / denominator
    return shift * dt, float(corr[i])


def analyze(traces, dt=0.001):
    result = {}
    read_traces = traces.get('standalone_read') or {}
    for name in sorted(set(traces['streaming']) & set(traces['standalone'])):
        streaming, standalone = traces['streaming'][name], traces['standalone'][name]
        read = read_traces.get(name)
        sources = [streaming, standalone] + ([read] if read else [])
        t0 = max(trace[0][0] for trace in sources) + 0.3  # skip edges
        t1 = min(trace[-1][0] for trace in sources) - 0.3
        if t1 - t0 < 2:
            continue
        grid = np.arange(t0, t1, dt)
        a, b = speed_on_grid(streaming, grid), speed_on_grid(standalone, grid)
        lag, corr = best_lag(a, b, dt)
        span = lambda trace: (trace[-1][0] - trace[0][0]) or 1.0
        result[name] = {'standalone_minus_streaming_ms': 1000 * lag, 'correlation': corr,
                        'streaming_samples_hz': len(streaming) / span(streaming),
                        'standalone_samples_hz': len(standalone) / span(standalone),
                        'mean_speed_m_s': float(a.mean()), 'window_s': t1 - t0}
        if read:
            # Absolute: both modes relative to the moment Frame read the pose.
            streaming_lag, streaming_corr = best_lag(speed_on_grid(read, grid), a, dt)
            transit = np.array([arrival[0] - r[0] for arrival, r in zip(standalone, read)]) * 1000
            result[name].update(
                streaming_latency_ms=1000 * streaming_lag, streaming_correlation=streaming_corr,
                standalone_latency_ms={'median': float(np.median(transit)),
                                       'p95': float(np.percentile(transit, 95)), 'max': float(transit.max())})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sender-ip', required=True, help='Frame address the standalone sender uses')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--seconds', type=float, default=20)
    parser.add_argument('--wait', type=float, default=300, help='Max seconds to wait for the first UDP packet')
    parser.add_argument('--label', help='Save results as artifacts/latency_<label>.json')
    parser.add_argument('--sync', action='store_true',
                        help='Measure the clock offset (sender must run with --sync) for absolute latency')
    parser.add_argument('--sync-port', type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    print(f'Polling PC SteamVR and waiting up to {args.wait:g} s for UDP from {args.sender_ip}...', flush=True)
    traces = capture(args.sender_ip, args.port, args.seconds, args.wait, args.sync_port if args.sync else None)
    result = analyze(traces)
    sync = traces.get('sync')
    if sync and 'error' in sync:
        print(f'Clock sync: {sync["error"]}')
    elif sync:
        print(f'Clock sync: offset {sync["offset_ms"]:+.3f} ms, RTT min {sync["rtt_min_ms"]:.2f} ms, '
              f'error bound +/-{sync["error_bound_ms"]:.2f} ms, {sync["bursts"]} bursts')
    if not result:
        print('No controller was seen by both sources long enough. Is the stream on and the sender running?')
    for name, r in result.items():
        quality = 'good' if r['correlation'] > 0.8 else 'weak: move more briskly' if r['correlation'] > 0.5 else 'unreliable'
        print(f'{name}: standalone arrives {r["standalone_minus_streaming_ms"]:+.1f} ms vs streaming '
              f'(correlation {r["correlation"]:.2f}, {quality}); samples: streaming '
              f'{r["streaming_samples_hz"]:.0f} Hz, standalone {r["standalone_samples_hz"]:.0f} Hz; '
              f'mean speed {r["mean_speed_m_s"]:.2f} m/s over {r["window_s"]:.1f} s')
        if 'streaming_latency_ms' in r:
            s = r['standalone_latency_ms']
            print(f'  absolute (from Frame pose read): standalone median {s["median"]:.2f} ms '
                  f'(p95 {s["p95"]:.2f}, max {s["max"]:.2f}); streaming {r["streaming_latency_ms"]:+.1f} ms '
                  f'(correlation {r["streaming_correlation"]:.2f})')
    if sync:
        result = {'controllers': result, 'sync': sync}
    if args.label:
        out = ARTIFACTS / f'latency_{args.label}.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(f'Saved {out}')


if __name__ == '__main__':
    main()
