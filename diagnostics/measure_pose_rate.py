"""Measure observed changes, not hardware timestamps or sensor sample rate."""
import time
from collections import defaultdict


def measure(reader, seconds=12.0, poll_sleep=0.001):
    """Poll reader much faster than the expected VR tracking rate; per-device change statistics."""
    last, changes, valid = {}, defaultdict(list), defaultdict(int)
    polls = 0
    start = time.perf_counter()
    deadline = start + seconds
    while time.perf_counter() < deadline:
        poses = reader.read()
        now = time.perf_counter()
        polls += 1
        for pose in poses.values():
            device = pose.device_id
            valid[device] += 1
            matrix = pose.T.tobytes()
            if device in last and matrix != last[device]:
                changes[device].append(now)
            last[device] = matrix
        time.sleep(poll_sleep)
    elapsed = time.perf_counter() - start
    stats = {'elapsed_s': elapsed, 'polls': polls, 'devices': {}}
    for device in sorted(valid):
        times = changes[device]
        intervals = sorted((b-a)*1000 for a, b in zip(times, times[1:]))
        entry = {'valid_polls': valid[device], 'changes': len(times), 'rate_hz': len(times)/elapsed}
        if intervals:
            median = intervals[len(intervals)//2]
            entry.update(min_ms=intervals[0], median_ms=median,
                         p95_ms=intervals[min(len(intervals)-1, int(len(intervals)*0.95))],
                         max_ms=intervals[-1], gaps=sum(i > 3*median for i in intervals))
        stats['devices'][device] = entry
    return stats


def report(stats):
    elapsed, polls = stats['elapsed_s'], stats['polls']
    print(f'Duration: {elapsed:.3f} s; polls: {polls}; polling rate: {polls/elapsed:.1f} Hz')
    for device, d in stats['devices'].items():
        print(f'Device {device}: valid polls={d["valid_polls"]}/{polls}; changed matrices={d["changes"]}; '
              f'observed change rate={d["rate_hz"]:.1f} Hz')
        if 'median_ms' in d:
            print(f'  Change intervals ms: min={d["min_ms"]:.3f}, median={d["median_ms"]:.3f}, '
                  f'p95={d["p95_ms"]:.3f}, max={d["max_ms"]:.3f}; gaps >3x median={d["gaps"]}')


def main():
    from general.config import Config
    from streaming.frame_pose import PoseReader
    reader = PoseReader(Config(fields=frozenset()))  # pose only
    try:
        report(measure(reader))
    finally:
        reader.close()


if __name__ == '__main__':
    main()
