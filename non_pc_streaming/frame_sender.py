"""Run on Frame's Linux ARM64 OS to send local controller poses over UDP."""
import argparse
import ipaddress
import math
from pathlib import Path
import platform
import secrets
import socket
import sys
import time
from general.pose_wire import encode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pc', required=True, help='PC IPv4 address on the same Wi-Fi')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--hz', type=float, default=90)
    parser.add_argument('--seconds', type=float)
    parser.add_argument('--demo', action='store_true', help='Synthetic UDP test, no OpenVR required')
    args = parser.parse_args()
    try:
        pc = str(ipaddress.IPv4Address(args.pc))
    except ValueError:
        parser.error('--pc must be an IPv4 address')
    if (not math.isfinite(args.hz) or not 0 < args.hz <= 1000
            or not 1 <= args.port <= 65535
            or args.seconds is not None and (not math.isfinite(args.seconds) or args.seconds <= 0)):
        parser.error('invalid rate, port, or duration')
    vr = None
    if not args.demo:
        if platform.system() != 'Linux' or platform.machine().lower() not in ('aarch64', 'arm64'):
            parser.error('live sender must run on Frame Linux ARM64; use --demo on the PC')
        sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
        try:
            import openvr as vr
            system = vr.init(vr.VRApplication_Background)
        except Exception as exc:
            raise SystemExit(f'Local OpenVR initialization failed: {exc}\n'
                             'Keep Frame awake in its local VR dashboard; PC streaming is not needed.\n'
                             'Check the vendor ARM64 library and local SteamVR runtime.')
        buffer = (vr.TrackedDevicePose_t * vr.k_unMaxTrackedDeviceCount)()
        event = vr.VREvent_t()
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
                quitting = False
                while system.pollNextEvent(event):
                    if event.eventType == vr.VREvent_Quit:
                        system.acknowledgeQuit_Exiting()
                        quitting = True
                if quitting:
                    break
                buffer = system.getDeviceToAbsoluteTrackingPose(vr.TrackingUniverseStanding, 0, buffer)
                roles = set()
                for device, pose in enumerate(buffer):
                    if (system.getTrackedDeviceClass(device) != vr.TrackedDeviceClass_Controller
                            or not pose.bDeviceIsConnected or not pose.bPoseIsValid
                            or pose.eTrackingResult != vr.TrackingResult_Running_OK):
                        continue
                    role = int(system.getControllerRoleForTrackedDeviceIndex(device))
                    role = role if role in (1, 2) and role not in roles else 0
                    roles.add(role)
                    matrix = [pose.mDeviceToAbsoluteTracking.m[r][c] for r in range(3) for c in range(4)]
                    entries.append((device, role, int(pose.eTrackingResult), matrix))
                    if len(entries) == 8:
                        break
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
