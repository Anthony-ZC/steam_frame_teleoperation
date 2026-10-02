"""Live controller positions, trajectories, and local orientation axes."""
import argparse
import time
from collections import deque
import numpy as np
from general.poses import DemoReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--udp', action='store_true', help='Receive poses directly from Frame, without PC SteamVR')
    parser.add_argument('--bind', default='0.0.0.0', help='UDP listening IPv4 address')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--sender-ip', help='Accept UDP packets only from this Frame IPv4 address')
    parser.add_argument('--timeout', type=float, default=0.25, help='Hide poses after this many seconds without a UDP packet')
    parser.add_argument('--hz', type=float, default=90)
    parser.add_argument('--full-redraw', action='store_true', help='Disable fast partial redraws')
    parser.add_argument('--benchmark', type=int, metavar='FRAMES', help='Render demo frames without a window and report speed')
    parser.add_argument('--span', type=float, default=2.0, help='View width in meters')
    parser.add_argument('--save-preview', help='Save a synthetic preview PNG and exit')
    args = parser.parse_args()
    if args.udp and args.demo:
        parser.error('--udp and --demo are mutually exclusive')
    if args.hz <= 0 or args.span <= 0:
        parser.error('hz and span must be positive')
    if args.save_preview and not args.demo:
        parser.error('--save-preview requires --demo')
    if args.benchmark is not None and (not args.demo or args.benchmark <= 0):
        parser.error('--benchmark requires --demo and a positive frame count')
    import matplotlib
    if args.save_preview or args.benchmark:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    try:
        if args.udp:
            from non_pc_streaming.udp_pose import UDPReader
            reader = UDPReader(args.bind, args.port, args.timeout, args.sender_ip)
            print(f'Listening for Frame poses on {args.bind}:{args.port}; stale timeout {args.timeout:g}s')
        else:
            if args.demo:
                reader = DemoReader()
            else:
                from streaming.frame_pose import PoseReader
                reader = PoseReader()
    except Exception as exc:
        hint = 'Check the UDP bind address/port.' if args.udp else 'Start SteamVR and connect Frame to the PC first.'
        raise SystemExit(f'Pose reader initialization failed: {exc}\n{hint}')
    try:
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        # Plot coordinates (X, -Z, Y) so physical up is the vertical plot axis.
        P = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        ax.set_xlabel('SteamVR X / right (m)')
        ax.set_ylabel('SteamVR -Z / forward (m)')
        ax.set_zlabel('SteamVR Y / up (m)')
        ax.set_box_aspect((1, 1, 1))
        title = ax.set_title('')
        trails, artists = {}, {}
        centered = False
        fast = fig.canvas.supports_blit and not args.full_redraw and not args.save_preview
        background = None
        last_status = None

        def moving_artists():
            return [art for group in artists.values() for art in group]

        def paint():
            if background is None:
                return
            fig.canvas.restore_region(background)
            for art in moving_artists():
                if art.get_visible():
                    ax.draw_artist(art)
            fig.canvas.blit(fig.bbox)

        def on_draw(_):
            nonlocal background
            if fast:
                background = fig.canvas.copy_from_bbox(fig.bbox)
                paint()

        fig.canvas.mpl_connect('draw_event', on_draw)

        def update(_):
            nonlocal centered, last_status
            redraw = False
            poses = reader.read()
            if poses and not centered:
                center = np.mean([P @ p.T[:3, 3] for p in poses.values()], axis=0)
                h = args.span / 2
                ax.set_xlim(center[0]-h, center[0]+h)
                ax.set_ylim(center[1]-h, center[1]+h)
                ax.set_zlim(center[2]-h, center[2]+h)
                centered = True
                redraw = True
            for name in artists.keys() - poses.keys():
                for art in artists[name]:
                    art.set_visible(False)
                trails[name].clear()  # don't connect a trail across lost tracking
            for name, pose in poses.items():
                if name not in artists:
                    color = {'left': 'tab:blue', 'right': 'tab:orange'}.get(name, 'gray')
                    trail, = ax.plot([], [], [], color=color, alpha=0.5)
                    marker, = ax.plot([], [], [], 'o', color=color, label=name)
                    axes = [ax.plot([], [], [], color=c, lw=2)[0] for c in ('r','g','b')]
                    artists[name] = [trail, marker, *axes]
                    for art in artists[name]:
                        art.set_animated(fast)
                    trails[name] = deque(maxlen=150)
                    ax.legend(loc='upper left')
                    redraw = True
                for art in artists[name]:
                    art.set_visible(True)
                p = P @ pose.T[:3, 3]
                R = P @ pose.T[:3, :3]
                trails[name].append(p)
                trail, marker, *axes = artists[name]
                trail.set_data_3d(np.array(trails[name]).T)
                marker.set_data_3d([p[0]], [p[1]], [p[2]])
                for j, art in enumerate(axes):
                    art.set_data_3d(np.stack([p, p + 0.12*R[:, j]]).T)
            status = ', '.join(sorted(poses)) or 'NONE: check tracking/connection'
            if status != last_status:
                label = 'SYNTHETIC DEMO' if args.demo else 'Live Frame UDP poses' if args.udp else 'Live SteamVR poses'
                title.set_text(f'{label}\n'
                               f'Tracked: {status} | local axes: X red, Y green, Z blue')
                last_status = status
                redraw = True
            if fast and background is not None and not redraw:
                paint()
            else:
                fig.canvas.draw()

        if args.save_preview:
            update(0)
            fig.savefig(args.save_preview, dpi=130, bbox_inches='tight')
            plt.close(fig)
        elif args.benchmark:
            update(0)
            start = time.perf_counter()
            for i in range(args.benchmark):
                update(i)
            elapsed = time.perf_counter() - start
            print(f'{"Partial" if fast else "Full"} redraw: {args.benchmark/elapsed:.1f} FPS; {1000*elapsed/args.benchmark:.2f} ms/frame')
            plt.close(fig)
        else:
            update(0)
            timer = fig.canvas.new_timer(interval=max(1, round(1000/args.hz)))
            timer.add_callback(update, 0)
            timer.start()
            fig.canvas.mpl_connect('close_event', lambda _: timer.stop())
            plt.show()
    finally:
        reader.close()


if __name__ == '__main__':
    main()
