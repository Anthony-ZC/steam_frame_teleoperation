"""Run on Frame's Linux ARM64 OS to send local controller poses over UDP."""
import argparse
import ipaddress
import math
import platform
import secrets
import socket
import time
from general import config as config_file
from general.pose_wire import MAX_CONTROLLERS, encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pc', required=True, help='PC IPv4 address on the same Wi-Fi')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--hz', type=float, default=90)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--demo', action='store_true', help='Synthetic UDP test, no OpenVR required')
    parser.add_argument('--config', help='config.toml path (default: repository config.toml)')
    args = parser.parse_args()
    try:
        pc = str(ipaddress.IPv4Address(args.pc))
    except ValueError:
        parser.error('--pc must be an IPv4 address')
    if (not math.isfinite(args.hz) or not 0 < args.hz <= 1000
            or not 1 <= args.port <= 65535
            or args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0)):
        parser.error('invalid rate, port, or duration')
    try:
        config = config_file.load(args.config)
    except (OSError, ValueError) as exc:
        parser.error(f'invalid config: {exc}')
    vr = None
    if not args.demo:
        if platform.system() != 'Linux' or platform.machine().lower() not in ('aarch64', 'arm64'):
            parser.error('live sender must run on Frame Linux ARM64; use --demo on the PC')
        from general.openvr_sampler import OpenVRSampler, init_openvr, load_openvr
        try:
            vr = load_openvr()
            system = init_openvr(vr, config.app_type)
        except Exception as exc:
            raise SystemExit(f'Local OpenVR initialization failed: {exc}\n'
                             'Keep Frame awake in its local VR dashboard; PC streaming is not needed.\n'
                             'Check the vendor ARM64 library and local SteamVR runtime.')
        # The FVR1 packet carries poses only, so no input groups are sampled yet.
        sampler = OpenVRSampler(vr, system, max_controllers=MAX_CONTROLLERS)
    session = secrets.randbits(64)
    sequence = 0
    start = next_tick = last_report = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f'{"DEMO" if args.demo else "LOCAL FRAME"}: sending to {pc}:{args.port} at {args.hz:g} Hz', flush=True)
    try:
        while args.seconds is None or time.monotonic() - start < args.seconds:
            now = time.monotonic()
            entries = []
            if args.demo:
                for device, role in ((1, 1), (2, 2)):
                    a = now - start + (math.pi if role == 2 else 0)
                    c, s = math.cos(a), math.sin(a)
                    matrix = [c, 0, s, (-0.3 if role == 1 else 0.3) + 0.12*c,
                              0, 1, 0, 1.2 + 0.08*math.sin(2*a),
                              -s, 0, c, -0.4 + 0.12*s]
                    entries.append((device, role, 200, matrix))
            else:
                states = sampler.sample()
                if sampler.quit_requested:
                    break
                for state in states.values():
                    role = {'left': 1, 'right': 2}.get(state.name, 0)
                    entries.append((state.device_id, role, state.tracking_result, state.matrix))
            sock.sendto(encode(session, sequence, time.monotonic_ns(), entries), (pc, args.port))
            sequence += 1
            if now - last_report >= 2:
                print(f'packets={sequence} controllers={len(entries)} elapsed={now-start:.1f}s', flush=True)
                last_report = now
            next_tick += 1 / args.hz
            delay = next_tick - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.monotonic()  # avoid bursts after a delayed cycle
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sock.sendto(encode(session, sequence, time.monotonic_ns(), []), (pc, args.port))
        finally:
            sock.close()
            if vr:
                vr.shutdown()


if __name__ == '__main__':
    main()
