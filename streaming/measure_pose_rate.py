"""Measure observed changes, not hardware timestamps or sensor sample rate."""
import time
from collections import defaultdict
from streaming.frame_pose import PoseReader

reader = PoseReader()
last = {}
changes = defaultdict(list)
valid = defaultdict(int)
polls = 0
duration = 12.0
try:
    start = time.perf_counter()
    deadline = start + duration
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
        # Poll much faster than the expected VR tracking rate.
        time.sleep(0.001)
    elapsed = time.perf_counter() - start
    print(f'Duration: {elapsed:.3f} s; polls: {polls}; polling rate: {polls/elapsed:.1f} Hz')
    for device in sorted(valid):
        times = changes[device]
        intervals = sorted((b-a)*1000 for a,b in zip(times,times[1:]))
        print(f'Device {device}: valid polls={valid[device]}/{polls}; changed matrices={len(times)}; observed change rate={len(times)/elapsed:.1f} Hz')
        if intervals:
            print(f'  Change intervals ms: min={intervals[0]:.3f}, median={intervals[len(intervals)//2]:.3f}, p95={intervals[min(len(intervals)-1,int(len(intervals)*0.95))]:.3f}, max={intervals[-1]:.3f}')
finally:
    reader.close()
