"""Print poses and inputs, optionally log them to CSV."""
import argparse
import csv
import time
from general import config as config_file
from general.controller_state import BUTTONS, FINGERS
from general.readers import DemoReader
from general.relative_pose import RelativePoseTracker


def csv_columns(fields):
    columns = ['received_monotonic_s', 'controller', 'device_id', 'tracking_result', 'pose_frame']
    columns += [f'T{r}{c}' for r in range(4) for c in range(4)]
    if 'velocity' in fields:
        columns += ['vx', 'vy', 'vz', 'wx', 'wy', 'wz']
    if 'battery' in fields:
        columns += ['battery', 'charging']
    if 'buttons' in fields:
        columns += [f'{b}_{kind}' for b in BUTTONS for kind in ('pressed', 'touched')]
    if 'analog' in fields:
        columns += ['trigger', 'grip', 'stick_x', 'stick_y']
    if 'fingers' in fields:
        columns += [f'curl_{f}' for f in FINGERS] + [f'splay_{i}' for i in range(4)]
    if fields & {'buttons', 'analog', 'fingers'}:
        columns.append('input_source')
    return columns


def csv_row(pose, frame, fields):
    s = pose.state
    blank = lambda n: [''] * n
    row = [pose.received_monotonic, pose.name, pose.device_id, pose.tracking_result, frame]
    row += pose.T.ravel().tolist()
    if 'velocity' in fields:
        row += (pose.velocity.tolist() + pose.angular_velocity.tolist()
                if pose.velocity is not None else blank(6))
    if 'battery' in fields:
        row += [s.battery, s.charging] if s else blank(2)
    if 'buttons' in fields:
        for b in BUTTONS:
            state = s.buttons.get(b) if s and s.buttons else None
            row += [int(state.pressed), int(state.touched)] if state else blank(2)
    if 'analog' in fields:
        row += ([s.trigger, s.grip, *(s.thumbstick or ('', ''))]
                if s and s.trigger is not None else blank(4))
    if 'fingers' in fields:
        row += (list(s.finger_curl) + list(s.finger_splay)
                if s and s.finger_curl else blank(9))
    if fields & {'buttons', 'analog', 'fingers'}:
        row.append(s.input_source if s else '')
    return ['' if v is None else v for v in row]


def describe(pose):
    s = pose.state
    parts = []
    if s and s.buttons:
        parts.append('buttons ' + ' '.join(f'{b}:{"P" if v.pressed else "t" if v.touched else "-"}'
                                           for b, v in s.buttons.items()))
    if s and s.trigger is not None:
        x, y = s.thumbstick or (0.0, 0.0)
        parts.append(f'trigger {s.trigger:.2f} grip {s.grip:.2f} stick ({x:+.2f}, {y:+.2f})')
    if s and s.finger_curl:
        parts.append('curl ' + ' '.join(f'{c:.2f}' for c in s.finger_curl))
    return '  '.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--hz', type=float, default=100)
    parser.add_argument('--csv', help='Optional CSV output path')
    parser.add_argument('--seconds', type=float, help='Stop after this duration')
    parser.add_argument('--config', help='config.toml path (default: repository config.toml)')
    args = parser.parse_args()
    if args.hz <= 0 or (args.seconds is not None and args.seconds <= 0):
        parser.error('hz and seconds must be positive')
    try:
        config = config_file.load(args.config)
    except (OSError, ValueError) as exc:
        parser.error(f'invalid config: {exc}')
    try:
        if args.demo:
            reader = DemoReader(config.fields)
        else:
            from streaming.frame_pose import SteamVRReader
            reader = SteamVRReader(config)
    except Exception as exc:
        raise SystemExit(f'OpenVR initialization failed: {exc}\n'
                         'Start SteamVR and connect Frame to the PC first.')
    tracker = (RelativePoseTracker(config.relative_mode, config.settle_seconds)
               if config.relative_enabled else None)
    output = None
    try:
        writer = None
        if args.csv:
            output = open(args.csv, 'w', newline='', encoding='utf-8')
            writer = csv.writer(output)
            writer.writerow(csv_columns(config.fields))
        start = time.monotonic()
        next_print = start
        while args.seconds is None or time.monotonic() - start < args.seconds:
            cycle = time.monotonic()
            poses = reader.read()
            frame = 'absolute'
            if tracker and tracker.remaining(cycle) == 0:
                poses, frame = tracker.apply(poses, cycle), f'relative_{config.relative_mode}'
            if cycle >= next_print:
                if not poses:
                    print('No fully tracked controllers. Check connection and camera visibility.')
                elif tracker and frame == 'absolute':
                    print(f'Capturing reference pose in {tracker.remaining(cycle):.1f} s; hold controllers still')
                for pose in poses.values():
                    print(f'{pose.name} (id={pose.device_id}, {frame})\n{pose.T.round(4)}\n  {describe(pose)}')
                next_print = cycle + 0.5
            if writer:
                for pose in poses.values():
                    writer.writerow(csv_row(pose, frame, config.fields))
            time.sleep(max(0, 1/args.hz - (time.monotonic() - cycle)))
    except KeyboardInterrupt:
        pass
    finally:
        if output:
            output.close()
        reader.close()


if __name__ == '__main__':
    main()
