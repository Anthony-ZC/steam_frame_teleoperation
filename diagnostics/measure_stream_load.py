"""Compare PC load and pose stability across streaming setups (Windows, Linux).

Run once per setup (stream off, desktop minimized, desktop shown, lower bitrate...),
then compare the saved runs:

  python -m diagnostics.measure_stream_load --label minimized --seconds 60
  python -m diagnostics.measure_stream_load --compare artifacts/stream_load_*.json

Load on Windows comes from performance counters (typeperf): total CPU, CPU of
vr*/steam* processes, and GPU utilization per engine type (3D, VideoEncode...);
processes started after the run begins are not counted. On Linux it comes from
/proc once per second (total CPU, vr*/steam* processes); there is no per-engine
GPU split, use the NVIDIA rows. Both add NVENC statistics when nvidia-smi
exists. Pose stability is measured as in measure_pose_rate.
"""
import argparse
import csv
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

COUNTERS = (r'\Processor(_Total)\% Processor Time', r'\Process(*)\% Processor Time',
            r'\GPU Engine(*)\Utilization Percentage')
ENGINE = re.compile(r'GPU Engine\(pid_\d+_luid_(\w+?)_(\w+?)_phys_(\d+)_eng_(\d+)_engtype_(.*)\)')
PROCESS = re.compile(r'\\Process\(([^)]*)\)')
ARTIFACTS = Path(__file__).resolve().parent.parent / 'artifacts'


def is_vr_process(name):
    name = name.split('#')[0].lower()
    return name.startswith('vr') or 'steam' in name


def aggregate(header, row, cores):
    """One typeperf sample -> {'cpu_total', 'gpu': {engtype: %}, 'processes': {name: % of all cores}}."""
    sample = {'cpu_total': None, 'gpu': {}, 'processes': defaultdict(float)}
    engines = defaultdict(float)  # one physical engine is shared by all processes using it
    for column, raw in zip(header[1:], row[1:]):
        try:
            value = float(raw)
        except ValueError:
            continue
        if 'Processor(_Total)' in column:
            sample['cpu_total'] = value
        elif match := ENGINE.search(column):
            *engine, engtype = match.groups()
            engines[(*engine, engtype)] += value
        elif (match := PROCESS.search(column)) and is_vr_process(match.group(1)):
            sample['processes'][match.group(1).split('#')[0]] += value / cores
    for (*_, engtype), value in engines.items():
        sample['gpu'][engtype] = max(sample['gpu'].get(engtype, 0.0), min(value, 100.0))
    sample['processes'] = dict(sample['processes'])
    return sample


def summary(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return {'mean': sum(values) / len(values), 'p95': values[min(len(values)-1, int(len(values)*0.95))],
            'max': values[-1]}


def read_typeperf(path, cores):
    with open(path, newline='', encoding='mbcs', errors='replace') as file:
        rows = [r for r in csv.reader(file) if r]
    header, samples = rows[0], [r for r in rows[1:] if len(r) == len(rows[0])]
    return [aggregate(header, row, cores) for row in samples]


def read_proc():
    """Linux: (total jiffies, idle jiffies, {(pid, name): cpu jiffies}) of all cores."""
    with open('/proc/stat', encoding='ascii') as file:
        values = [int(v) for v in file.readline().split()[1:]]
    processes = {}
    for stat in Path('/proc').glob('[0-9]*/stat'):
        try:
            text = stat.read_text(encoding='utf-8', errors='replace')
        except OSError:  # process ended
            continue
        name, fields = text[text.find('(') + 1:text.rfind(')')], text[text.rfind(')') + 2:].split()
        if is_vr_process(name):
            processes[(stat.parent.name, name)] = int(fields[11]) + int(fields[12])  # utime + stime
    return sum(values[:8]), values[3] + values[4], processes  # idle + iowait


def poll_proc(stop, samples):
    """Linux: one sample per second in the shape of aggregate(); new processes are included."""
    previous = read_proc()
    while not stop.wait(1.0):
        current = read_proc()
        total = current[0] - previous[0]
        if total > 0:
            processes = defaultdict(float)
            for key, jiffies in current[2].items():  # a new pid's jiffies all fall in this interval
                processes[key[1]] += 100 * (jiffies - previous[2].get(key, 0)) / total
            samples.append({'cpu_total': 100 * (1 - (current[1] - previous[1]) / total), 'gpu': {},
                            'processes': dict(processes)})
        previous = current


def poll_nvidia(stop, results):
    query = 'utilization.gpu,utilization.encoder,encoder.stats.sessionCount,encoder.stats.averageFps'
    while not stop.wait(1.0):
        try:
            out = subprocess.run(['nvidia-smi', f'--query-gpu={query}', '--format=csv,noheader,nounits'],
                                 capture_output=True, text=True, timeout=5).stdout.splitlines()[0]
            results.append([float(v) for v in out.split(',')])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass


def measure_poses(seconds, result):
    from diagnostics.measure_pose_rate import measure
    from general.config import Config
    try:
        from streaming.frame_pose import SteamVRReader
        reader = SteamVRReader(Config(fields=frozenset()))  # pose only: keep the probe itself light
    except Exception as exc:
        result['pose_error'] = f'{type(exc).__name__}: {exc}'
        time.sleep(seconds)  # still cover the load window
        return
    try:
        result['pose'] = measure(reader, seconds)
    finally:
        reader.close()


def run(label, seconds):
    cores = os.cpu_count() or 1
    windows = os.name == 'nt'
    with tempfile.TemporaryDirectory() as tmp:
        counters_csv = Path(tmp, 'counters.csv')
        stop, nvidia, samples = threading.Event(), [], []
        if windows:
            typeperf = subprocess.Popen(['typeperf', *COUNTERS, '-si', '1', '-sc', str(int(seconds)),
                                         '-f', 'CSV', '-o', str(counters_csv), '-y'],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            proc = threading.Thread(target=poll_proc, args=(stop, samples), daemon=True)
            proc.start()
        if shutil.which('nvidia-smi'):
            threading.Thread(target=poll_nvidia, args=(stop, nvidia), daemon=True).start()
        result = {'label': label, 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'seconds': seconds,
                  'cores': cores, 'platform': sys.platform, 'pose': None, 'pose_error': None}
        measure_poses(seconds, result)
        stop.set()
        if windows:
            try:
                typeperf.wait(timeout=30)
            except subprocess.TimeoutExpired:
                typeperf.kill()
            samples = read_typeperf(counters_csv, cores) if counters_csv.exists() else []
        else:
            proc.join(timeout=5)
    result['load_samples'] = len(samples)
    result['cpu_total'] = summary(s['cpu_total'] for s in samples)
    engtypes = sorted({e for s in samples for e in s['gpu']})
    result['gpu'] = {e: summary(s['gpu'].get(e, 0.0) for s in samples) for e in engtypes}
    names = {n for s in samples for n in s['processes']}
    processes = {n: summary(s['processes'].get(n, 0.0) for s in samples)['mean'] for n in names}
    result['vr_processes_cpu'] = dict(sorted(processes.items(), key=lambda kv: -kv[1]))
    result['vr_processes_cpu_total'] = sum(processes.values())
    if nvidia:
        columns = list(zip(*nvidia))
        result['nvidia'] = {'gpu_util': summary(columns[0]), 'encoder_util': summary(columns[1]),
                            'encoder_sessions_max': max(columns[2]), 'encoder_fps': summary(columns[3])}
    return result


def print_run(r):
    print(f'=== {r["label"]} ({r["started"]}, {r["seconds"]:g} s, {r["load_samples"]} load samples) ===')
    if r['cpu_total']:
        print(f'CPU total: mean {r["cpu_total"]["mean"]:.1f}%  p95 {r["cpu_total"]["p95"]:.1f}%')
    print(f'VR/Steam processes CPU: {r["vr_processes_cpu_total"]:.2f}% of all cores')
    for name, value in list(r['vr_processes_cpu'].items())[:8]:
        print(f'  {name:24} {value:.2f}%')
    for engtype, s in r['gpu'].items():
        if s and s['max'] > 0.5:
            print(f'GPU {engtype:14} mean {s["mean"]:5.1f}%  p95 {s["p95"]:5.1f}%')
    if r.get('nvidia'):
        n = r['nvidia']
        print(f'NVIDIA GPU utilization: mean {n["gpu_util"]["mean"]:.1f}%  p95 {n["gpu_util"]["p95"]:.1f}%')
        print(f'NVENC: utilization mean {n["encoder_util"]["mean"]:.1f}%, sessions {n["encoder_sessions_max"]:g}, '
              f'avg fps {n["encoder_fps"]["mean"]:.1f}')
    if r['pose']:
        from diagnostics.measure_pose_rate import report
        report(r['pose'])
    else:
        print(f'Poses: not measured ({r["pose_error"]})')


def compare(paths):
    runs = [json.loads(Path(p).read_text(encoding='utf-8')) for p in paths]
    fmt = lambda v, spec='.1f': '-' if v is None else format(v, spec)
    get = lambda d, *keys: d if not keys or d is None else get(d.get(keys[0]), *keys[1:])
    rows = [('CPU total mean %', lambda r: get(r, 'cpu_total', 'mean')),
            ('CPU total p95 %', lambda r: get(r, 'cpu_total', 'p95')),
            ('VR/Steam proc CPU %', lambda r: r.get('vr_processes_cpu_total')),
            ('GPU 3D mean %', lambda r: get(r, 'gpu', '3D', 'mean')),
            ('GPU VideoEncode mean %', lambda r: get(r, 'gpu', 'VideoEncode', 'mean')),
            ('NVIDIA GPU util mean %', lambda r: get(r, 'nvidia', 'gpu_util', 'mean')),
            ('NVENC util mean %', lambda r: get(r, 'nvidia', 'encoder_util', 'mean')),
            ('NVENC sessions', lambda r: get(r, 'nvidia', 'encoder_sessions_max')),
            ('NVENC avg fps', lambda r: get(r, 'nvidia', 'encoder_fps', 'mean'))]
    devices = sorted({d for r in runs for d in (get(r, 'pose', 'devices') or {})})
    for d in devices:
        for key, title in (('rate_hz', 'pose rate Hz'), ('median_ms', 'median ms'),
                           ('p95_ms', 'p95 ms'), ('max_ms', 'max ms'), ('gaps', 'gaps >3x median')):
            rows.append((f'dev {d} {title}', lambda r, d=d, k=key: get(r, 'pose', 'devices', d, k)))
    width = max(12, *(len(r['label']) for r in runs))
    print(f'{"":24}' + ''.join(f'{r["label"]:>{width + 2}}' for r in runs))
    for title, value in rows:
        print(f'{title:24}' + ''.join(f'{fmt(value(r)):>{width + 2}}' for r in runs))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--label', help='Name of this setup, e.g. minimized')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--out', help='JSON output path (default artifacts/stream_load_<label>.json)')
    parser.add_argument('--compare', nargs='+', metavar='JSON', help='Compare saved runs instead of measuring')
    args = parser.parse_args()
    if args.compare:
        paths = [p for pattern in args.compare for p in sorted(glob.glob(pattern)) or [pattern]]
        return compare(paths)
    if not args.label or not re.fullmatch(r'[\w.-]+', args.label):
        parser.error('--label is required (letters, digits, _ . -)')
    if not 5 <= args.seconds <= 3600:
        parser.error('--seconds must be in [5, 3600]')
    print(f'Measuring "{args.label}" for {args.seconds:g} s; keep the setup unchanged...')
    result = run(args.label, args.seconds)
    out = Path(args.out) if args.out else ARTIFACTS / f'stream_load_{args.label}.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print_run(result)
    print(f'\nSaved {out}')


if __name__ == '__main__':
    main()
