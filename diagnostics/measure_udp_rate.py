"""Measure the standalone UDP data flow: rate, loss, jitter, pose update rate.

Close the viewer first (it uses the same port), then start the sender on Frame:

  python -m diagnostics.measure_udp_rate --sender-ip FRAME_IP --seconds 30

It waits up to --wait seconds for the first packet, then measures for --seconds.
Clocks are not synchronized, so latency is reported as variation above the
fastest packet (one-way delay jitter), not as an absolute value; a sender on
this PC (127.0.0.1) shares the clock, so its latency is reported absolutely.

Runtimes extrapolate poses, so a changed position does not prove new tracking
data. The velocity only changes with a real tracking update, so "tracking
updates" counts velocity changes (needs the velocity field group).
"""
import argparse
import json
import socket
import time
from pathlib import Path
from general.pose_wire import MAX_PACKET, decode

ARTIFACTS = Path(__file__).resolve().parent.parent / 'artifacts'


def percentiles(values):
    values = sorted(values)
    if not values:
        return None
    pick = lambda q: values[min(len(values) - 1, int(len(values) * q))]
    return {'min': values[0], 'median': pick(0.5), 'p95': pick(0.95), 'p99': pick(0.99), 'max': values[-1]}


def measure(port=9000, sender_ip=None, seconds=30.0, wait=120.0, bind='0.0.0.0'):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((bind, port))
    except OSError as exc:
        sock.close()
        raise SystemExit(f'Cannot listen on UDP {port}: {exc}\n'
                         'Another program (usually the viewer with --udp) is using it; close it first.')
    sock.settimeout(0.2)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)  # absorb unlimited-rate bursts
    packets = []  # (receive ns, sequence, sender ns, groups, {name: (matrix, velocity)})
    rejected = {}  # reason -> count, so stray senders are visible
    deadline = time.monotonic() + wait
    try:
        while True:
            now = time.monotonic()
            if (packets and now >= end) or (not packets and now >= deadline):
                break
            try:
                payload, source = sock.recvfrom(MAX_PACKET + 1)
            except socket.timeout:
                continue
            received = time.perf_counter_ns()  # monotonic_ns ticks only every ~15.6 ms on Windows
            if sender_ip and source[0] != sender_ip:
                key = f'other source {source[0]}'
                rejected[key] = rejected.get(key, 0) + 1
                continue
            try:
                session, sequence, sender_ns, groups, states = decode(payload)
            except (ValueError, OverflowError):
                rejected['malformed'] = rejected.get('malformed', 0) + 1
                continue
            if not packets:
                end = time.monotonic() + seconds
                first_session = session
            if session != first_session:
                # Another sender process on the same address (e.g. an old one still running).
                key = f'other session from {source[0]}'
                rejected[key] = rejected.get(key, 0) + 1
                continue
            packets.append((received, sequence, sender_ns, groups,
                            {s.name: (tuple(s.matrix), s.velocity) for s in states}))
    finally:
        sock.close()
    return analyze(packets, rejected, same_clock=sender_ip in ('127.0.0.1', 'localhost'))


def analyze(packets, rejected=None, same_clock=False):
    result = {'packets': len(packets), 'rejected': rejected or {}}
    if len(packets) < 2:
        return result
    duration = (packets[-1][0] - packets[0][0]) / 1e9
    sequences = [p[1] for p in packets]
    expected = max(sequences) - min(sequences) + 1
    unique = len(set(sequences))
    reordered = sum(b < a for a, b in zip(sequences, sequences[1:]))
    arrival = [(b[0] - a[0]) / 1e6 for a, b in zip(packets, packets[1:])]
    sent = [(b[2] - a[2]) / 1e6 for a, b in zip(packets, packets[1:]) if b[1] > a[1]]
    offsets = [p[0] - p[2] for p in packets]  # receive - send, includes an unknown clock offset
    best = min(offsets)
    arrival_stats = percentiles(arrival)
    result.update(
        duration_s=duration, rate_hz=(len(packets) - 1) / duration,
        lost=expected - unique, loss_pct=100 * (expected - unique) / expected,
        duplicates=len(packets) - unique, reordered=reordered,
        groups=sorted(packets[-1][3]),
        arrival_ms=arrival_stats, send_ms=percentiles(sent),
        arrival_gaps=sum(i > 3 * arrival_stats['median'] for i in arrival),
        delay_jitter_ms=percentiles([(o - best) / 1e6 for o in offsets]),
        latency_ms=percentiles([o / 1e6 for o in offsets]) if same_clock else None,
        controllers={})
    names = sorted({n for p in packets for n in p[4]})
    for name in names:
        present = [p for p in packets if name in p[4]]
        changes = [b[0] for a, b in zip(present, present[1:]) if b[4][name][0] != a[4][name][0]]
        tracked = [b[0] for a, b in zip(present, present[1:])
                   if b[4][name][1] is not None and b[4][name][1] != a[4][name][1]]
        has_velocity = any(p[4][name][1] is not None for p in present)
        result['controllers'][name] = {
            'present_pct': 100 * len(present) / len(packets),
            'pose_update_hz': len(changes) / duration,
            'repeated_pct': 100 * (1 - len(changes) / max(1, len(present) - 1)),
            'update_interval_ms': percentiles([(b - a) / 1e6 for a, b in zip(changes, changes[1:])]),
            'tracking_update_hz': len(tracked) / duration if has_velocity else None,
            'tracking_interval_ms': percentiles([(b - a) / 1e6 for a, b in zip(tracked, tracked[1:])])}
    return result


def report(r):
    reasons = ', '.join(f'{n} {why}' for why, n in r['rejected'].items())
    print(f'Packets: {r["packets"]} accepted, {sum(r["rejected"].values())} rejected'
          + (f' ({reasons})' if reasons else ''))
    if 'rate_hz' not in r:
        print('Not enough packets: is the sender running and the viewer closed?')
        return
    fmt = lambda s: (f'median {s["median"]:.2f}, p95 {s["p95"]:.2f}, p99 {s["p99"]:.2f}, max {s["max"]:.2f}'
                     if s else '-')
    print(f'Duration {r["duration_s"]:.1f} s; arrival rate {r["rate_hz"]:.1f} Hz; groups: {", ".join(r["groups"]) or "pose only"}')
    print(f'Loss: {r["lost"]} packets ({r["loss_pct"]:.2f}%), duplicates {r["duplicates"]}, reordered {r["reordered"]}')
    print(f'Arrival interval ms: {fmt(r["arrival_ms"])}; gaps >3x median: {r["arrival_gaps"]}')
    print(f'Send interval ms (Frame clock): {fmt(r["send_ms"])}')
    print(f'One-way delay variation ms (above fastest packet): {fmt(r["delay_jitter_ms"])}')
    if r.get('latency_ms'):
        print(f'One-way latency ms (same clock, sender on this PC): {fmt(r["latency_ms"])}')
    for name, c in r['controllers'].items():
        print(f'{name}: present {c["present_pct"]:.1f}% of packets; new pose {c["pose_update_hz"]:.1f} Hz '
              f'({c["repeated_pct"]:.1f}% repeated); update interval ms: {fmt(c["update_interval_ms"])}')
        if c['tracking_update_hz'] is not None:
            print(f'  tracking updates (velocity changes) {c["tracking_update_hz"]:.1f} Hz; '
                  f'interval ms: {fmt(c["tracking_interval_ms"])}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--sender-ip', help='Accept packets only from this IPv4 address')
    parser.add_argument('--seconds', type=float, default=30, help='Measurement length after the first packet')
    parser.add_argument('--wait', type=float, default=120, help='Max seconds to wait for the first packet')
    parser.add_argument('--label', help='Save results as artifacts/udp_rate_<label>.json')
    args = parser.parse_args()
    print(f'Listening on {args.bind}:{args.port}; waiting up to {args.wait:g} s for the first packet...', flush=True)
    result = measure(args.port, args.sender_ip, args.seconds, args.wait, args.bind)
    report(result)
    if args.label:
        out = ARTIFACTS / f'udp_rate_{args.label}.json'
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(f'Saved {out}')


if __name__ == '__main__':
    main()
