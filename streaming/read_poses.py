"""Print full homogeneous transforms, optionally log them to CSV."""
import argparse
import csv
import time
from streaming.frame_pose import PoseReader
from general.poses import DemoReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--hz', type=float, default=100)
    parser.add_argument('--csv', help='Optional CSV output path')
    parser.add_argument('--seconds', type=float, help='Stop after this duration')
    args = parser.parse_args()
    if args.hz <= 0 or (args.seconds is not None and args.seconds <= 0):
        parser.error('hz and seconds must be positive')
    try:
        reader = DemoReader() if args.demo else PoseReader()
    except Exception as exc:
        raise SystemExit(f'OpenVR initialization failed: {exc}\n'
                         'Start SteamVR and connect Frame to the PC first.')
    output = None
    try:
        writer = None
        if args.csv:
            output = open(args.csv, 'w', newline='', encoding='utf-8')
            writer = csv.writer(output)
            writer.writerow(['received_monotonic_s', 'controller', 'device_id',
                             'tracking_result'] + [f'T{r}{c}' for r in range(4) for c in range(4)])
        start = time.monotonic()
        next_print = start
        while args.seconds is None or time.monotonic() - start < args.seconds:
            cycle = time.monotonic()
            poses = reader.read()
            if cycle >= next_print:
                if not poses:
                    print('No fully tracked controllers. Check connection and camera visibility.')
                for pose in poses.values():
                    print(f'{pose.name} (id={pose.device_id})\n{pose.T.round(4)}')
                next_print = cycle + 0.5
            if writer:
                for pose in poses.values():
                    writer.writerow([pose.received_monotonic, pose.name, pose.device_id,
                                     pose.tracking_result] + pose.T.ravel().tolist())
            time.sleep(max(0, 1/args.hz - (time.monotonic() - cycle)))
    except KeyboardInterrupt:
        pass
    finally:
        if output:
            output.close()
        reader.close()


if __name__ == '__main__':
    main()
