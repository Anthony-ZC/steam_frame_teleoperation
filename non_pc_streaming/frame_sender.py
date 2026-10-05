"""Run on Frame's Linux ARM64 OS to send local controller poses and inputs over UDP."""
import argparse
import ipaddress
import math
import platform
import secrets
import socket
import time
from general import config as config_file
from general.demo import demo_states
from general.pose_wire import GROUP_BITS, MAX_CONTROLLERS, encode_states


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pc', required=True, help='PC IPv4 address on the same Wi-Fi')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--hz', type=float, default=90, help='Send rate; 0 = unlimited (as fast as sampling allows)')
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--demo', action='store_true', help='Synthetic UDP test, no OpenVR required')
    parser.add_argument('--desktop', action='store_true',
                        help='Allow live mode off Frame (e.g. against PC SteamVR) to test the UDP path')
    parser.add_argument('--config', help='config.toml path (default: repository config.toml)')
    parser.add_argument('--sync', action='store_true',
                        help='Answer clock-sync requests from the PC (absolute latency measurement)')
    parser.add_argument('--sync-port', type=int, default=9001)
    args = parser.parse_args()
    try:
        pc = str(ipaddress.IPv4Address(args.pc))
    except ValueError:
        parser.error('--pc must be an IPv4 address')
    if (not math.isfinite(args.hz) or not 0 <= args.hz <= 1000
            or not 1 <= args.port <= 65535
            or args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0)):
        parser.error('invalid rate, port, or duration')
    if args.demo and args.desktop:
        parser.error('--demo and --desktop are mutually exclusive')
    try:
        config = config_file.load(args.config)
    except (OSError, ValueError) as exc:
        parser.error(f'invalid config: {exc}')
    # Optional data: exactly the [fields] groups enabled in config.toml are sent.
    groups = [g for g in GROUP_BITS if g in config.fields]
    vr = None
    if not args.demo:
        on_frame = platform.system() == 'Linux' and platform.machine().lower() in ('aarch64', 'arm64')
        if not on_frame and not args.desktop:
            parser.error('live sender must run on Frame Linux ARM64; use --demo, or --desktop for PC SteamVR')
        from general.openvr_sampler import OpenVRSampler, init_openvr, load_openvr, runtime_report
        try:
            vr = load_openvr()
            system = init_openvr(vr, config.app_type)
        except Exception as exc:
            raise SystemExit(f'Local OpenVR initialization failed: {type(exc).__name__}: {exc}\n'
                             'Keep Frame awake in its local VR dashboard; PC streaming is not needed.\n'
                             + '\n'.join(runtime_report()))
        sampler = OpenVRSampler(vr, system, config.fields, config.legacy_fallback, MAX_CONTROLLERS)
        if sampler.input_error:
            print(f'SteamVR Input unavailable: {sampler.input_error}', flush=True)
    session = secrets.randbits(64)
    sequence = 0
    # perf_counter: monotonic and fine-grained on every OS (monotonic() ticks every ~15.6 ms on Windows).
    start = next_tick = last_report = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    responder = None
    if args.sync:  # optional: normal use opens no extra port
        from general.clock_sync import Responder
        responder = Responder(args.sync_port, allowed_ip=pc)
        print(f'Clock sync: answering {pc} on UDP {args.sync_port}', flush=True)
    mode = 'DEMO' if args.demo else 'DESKTOP' if args.desktop else 'LOCAL FRAME'
    rate = f'{args.hz:g} Hz' if args.hz else 'unlimited rate'
    print(f'{mode}: sending to {pc}:{args.port} at {rate}; '
          f'groups: {", ".join(groups) or "pose only"}', flush=True)
    try:
        while args.seconds is None or time.perf_counter() - start < args.seconds:
            now = time.perf_counter()
            if args.demo:
                states = demo_states(now - start, config.fields)
            else:
                states = sampler.sample()
                if sampler.quit_requested:
                    break
            read_ns = time.perf_counter_ns()  # packet timestamp = pose read time
            sock.sendto(encode_states(session, sequence, read_ns, list(states.values()), groups),
                        (pc, args.port))
            sequence += 1
            if now - last_report >= 2:
                blocked = not args.demo and sampler.dashboard_visible
                print(f'packets={sequence} controllers={len(states)} elapsed={now-start:.1f}s'
                      + (' (SteamVR dashboard open: no button/finger input)' if blocked else ''), flush=True)
                last_report = now
            if not args.hz:
                continue  # unlimited: sample and send again immediately
            next_tick += 1 / args.hz
            delay = next_tick - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            else:
                next_tick = time.perf_counter()  # avoid bursts after a delayed cycle
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sock.sendto(encode_states(session, sequence, time.perf_counter_ns(), [], groups), (pc, args.port))
        finally:
            sock.close()
            if responder:
                responder.close()
            if vr:
                vr.shutdown()


if __name__ == '__main__':
    main()
