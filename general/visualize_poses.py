"""Live controller poses (relative to a captured reference), buttons and finger curl."""
import argparse
import time
from collections import deque
import numpy as np
from general import config as config_file
from general.controller_state import FINGERS
from general.readers import DemoReader
from general.relative_pose import RelativePoseTracker, euler_yxz_deg

COLORS = {'left': 'tab:blue', 'right': 'tab:orange'}
FINGER_LABELS = ('thumb\nface', 'index\ntrigger', 'middle\ngrip', 'ring\ngrip', 'pinky\ngrip')
# Right controller: A/B/X/Y. Left controller: the mirrored d-pad.
FACE_LABELS = ({'a': 'A', 'b': 'B', 'x': 'X', 'y': 'Y'},
               {'a': '▼', 'b': '▶', 'x': '◀', 'y': '▲'})
IDLE_FACE, IDLE_EDGE = '#f0f0f0', '#b0b0b0'
TEXT_HZ = 10


class ControllerPanel:
    """'Hand + controller' panel for one controller, drawn in a 10 x 7 data box.

    Lamps: grey = idle, colored outline = touched, filled = pressed, dotted = no data.
    `shapes` are redrawn every frame; `texts` are slower to render and only
    need refreshing at a few Hz.
    """
    def __init__(self, ax, name, fields, animated):
        from matplotlib.patches import Circle, Rectangle
        from matplotlib.colors import to_rgba
        self.fields = fields
        self.color = COLORS[name]
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 7)
        ax.set_aspect('equal')
        ax.axis('off')
        ax.text(0.1, 6.95, name.upper(), color=self.color, fontsize=11, weight='bold', va='top')
        self.status = ax.text(1.5, 6.9, '', fontsize=8, va='top', color='dimgray')
        self.info = ax.text(0.1, 0.05, '', fontsize=7.5, family='monospace', va='bottom')
        self.texts, self.shapes = [self.status, self.info], []
        self.bars = []
        if 'fingers' in fields:
            ax.text(0.25, 6.25, 'finger curl (shade = splay)', fontsize=7, color='dimgray')
            for i, label in enumerate(FINGER_LABELS):
                x = 0.25 + i*0.8
                ax.add_patch(Rectangle((x, 1.95), 0.55, 3.95, fill=False, ec=IDLE_EDGE))
                ax.text(x + 0.28, 1.85, label, ha='center', va='top', fontsize=6.5)
                self.bars.append(ax.add_patch(Rectangle((x, 1.95), 0.55, 0, color=self.color)))
            self.shapes += self.bars
        self.lamps, self.levels = {}, {}

        def lamp(button, patch, alpha, label, dx=0.0, dy=-0.3, ha='center', va='top'):
            ax.add_patch(patch)
            self.lamps[button] = (patch, alpha)
            self.shapes.append(patch)
            x, y = patch.get_center() if isinstance(patch, Circle) else (patch.get_x() + patch.get_width()/2, patch.get_y())
            ax.text(x + dx, y + dy, label, ha=ha, va=va, fontsize=6.5)

        if 'analog' in fields or 'buttons' in fields:
            for row, button in ((4.85, 'trigger'), (3.85, 'grip')):
                lamp(button, Rectangle((5.55, row), 1.9, 0.55, lw=1), 0.3, button,
                     dx=-1.05, dy=0.28, ha='right', va='center')
                level = ax.add_patch(Rectangle((5.55, row), 0, 0.55, color=to_rgba(self.color, 0.6)))
                self.levels[button] = level
                self.shapes.append(level)
            lamp('thumbstick', Circle((8.95, 5.0), 0.7, lw=1), 0.3, 'stick', dy=-0.75)
            self.stick_dot = ax.add_patch(Circle((8.95, 5.0), 0.14, color=self.color))
            self.shapes.append(self.stick_dot)
        if 'buttons' in fields:
            lamp('bumper', Rectangle((4.7, 5.95), 1.0, 0.4, lw=1), 0.85, 'bumper', dy=-0.05)
            for x, button, label in ((6.35, 'menu', 'view' if name == 'left' else 'menu'),
                                     (7.05, 'system', 'sys'), (7.75, 'thumbrest', 'rest')):
                lamp(button, Circle((x, 6.15), 0.2, lw=1), 0.85, label, dy=-0.25)
            labels = FACE_LABELS[name == 'left']
            for button, (dx, dy) in {'y': (0, 0.55), 'x': (-0.55, 0), 'b': (0.55, 0), 'a': (0, -0.55)}.items():
                ox, oy = 0.36 * (dx > 0) - 0.36 * (dx < 0), 0.36 * (dy > 0) - 0.36 * (dy < 0)
                lamp(button, Circle((8.95 + dx, 2.75 + dy), 0.23, lw=1), 0.85, labels[button],
                     dx=ox, dy=oy, ha='center', va='center')
        if fields & {'buttons', 'analog'}:
            ax.text(4.7, 1.45, 'grey idle | outline touched | filled pressed | dotted no data',
                    fontsize=6, color='dimgray')
        else:
            ax.text(5.2, 4.0, 'buttons/analog disabled\nin config.toml', fontsize=8, color='dimgray')
        for art in self.texts + self.shapes:
            art.set_animated(animated)

    def _style(self, button, state):
        from matplotlib.colors import to_rgba
        patch, alpha = self.lamps[button]
        if state is None:
            patch.set(facecolor='none', edgecolor=IDLE_EDGE, linewidth=1, linestyle=':')
        elif state.pressed:
            patch.set(facecolor=to_rgba(self.color, alpha), edgecolor=self.color, linewidth=2.5, linestyle='-')
        elif state.touched:
            patch.set(facecolor=IDLE_FACE, edgecolor=self.color, linewidth=2.5, linestyle='-')
        else:
            patch.set(facecolor=IDLE_FACE, edgecolor=IDLE_EDGE, linewidth=1, linestyle='-')

    def update(self, pose, shown, frame_label):
        s = pose.state if pose else None
        curl = s.finger_curl if s else None
        splay = s.finger_splay if s else None
        for i, bar in enumerate(self.bars):
            bar.set_height(3.95 * min(max(curl[i], 0.0), 1.0) if curl else 0.0)
            bar.set_alpha(0.35 + 0.65*splay[min(i, 3)] if splay else 0.8)
        buttons = s.buttons if s else None
        for button in self.lamps:
            self._style(button, buttons.get(button) if buttons else None)
        for button, level in self.levels.items():
            value = getattr(s, button) if s else None
            level.set_width(1.9 * min(max(value or 0.0, 0.0), 1.0))
        if self.levels:
            x, y = s.thumbstick if s and s.thumbstick else (0.0, 0.0)
            self.stick_dot.set_center((8.95 + 0.7*max(-1, min(1, x)), 5.0 + 0.7*max(-1, min(1, y))))
            self.stick_dot.set_visible(bool(s and s.thumbstick))
        self._update_text(pose, s, shown, frame_label)

    def _update_text(self, pose, s, shown, frame_label):
        if pose is None:
            self.status.set_text('not tracked')
            self.info.set_text('')
            return
        parts = [(s.controller_type or '') if s else '']
        if s and s.battery is not None:
            parts.append(f'battery {100*s.battery:.0f}%' + (' charging' if s.charging else ''))
        if self.fields & {'buttons', 'analog', 'fingers'}:
            parts.append(f'input: {(s.input_source if s else None) or "none"}')
        self.status.set_text('   '.join(p for p in parts if p))
        lines = []
        if shown is None:
            lines.append(f'{frame_label}: waiting for reference')
        else:
            p, (roll, pitch, yaw) = shown.T[:3, 3], euler_yxz_deg(shown.T[:3, :3])
            lines.append(f'{frame_label} xyz [{p[0]:+.3f} {p[1]:+.3f} {p[2]:+.3f}] m'
                         f'  rpy [{roll:+6.1f} {pitch:+6.1f} {yaw:+6.1f}] deg')
            if shown.velocity is not None:
                lines.append(f'|v| {np.linalg.norm(shown.velocity):.2f} m/s'
                             f'  |w| {np.linalg.norm(shown.angular_velocity):.2f} rad/s'
                             f'  tracking {shown.tracking_result}')
        if s and s.finger_curl:
            lines.append('curl ' + ' '.join(f'{f[0].upper()} {c:.2f}' for f, c in zip(FINGERS, s.finger_curl)))
        if s and s.trigger is not None:
            x, y = s.thumbstick or (0.0, 0.0)
            lines.append(f'trigger {s.trigger:.2f}  grip {s.grip:.2f}  stick ({x:+.2f}, {y:+.2f})')
        self.info.set_text('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true')
    parser.add_argument('--udp', action='store_true', help='Receive poses directly from Frame, without PC SteamVR')
    parser.add_argument('--bind', default='0.0.0.0', help='UDP listening IPv4 address')
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--sender-ip', help='Accept UDP packets only from this Frame IPv4 address')
    parser.add_argument('--timeout', type=float, default=0.25, help='Hide poses after this many seconds without a UDP packet')
    parser.add_argument('--config', help='config.toml path (default: repository config.toml)')
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
    try:
        config = config_file.load(args.config)
    except (OSError, ValueError) as exc:
        parser.error(f'invalid config: {exc}')
    import matplotlib
    if args.save_preview or args.benchmark:
        matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.widgets import Button
    try:
        if args.udp:
            from non_pc_streaming.udp_pose import UDPReader
            reader = UDPReader(args.bind, args.port, args.timeout, args.sender_ip)
            print(f'Listening for Frame poses on {args.bind}:{args.port}; stale timeout {args.timeout:g}s')
        elif args.demo:
            reader = DemoReader(config.fields)
        else:
            from streaming.frame_pose import SteamVRReader
            reader = SteamVRReader(config)
            if reader.sampler.input_error:
                print(f'SteamVR Input unavailable ({reader.sampler.input_error}); using legacy state only')
    except Exception as exc:
        hint = 'Check the UDP bind address/port.' if args.udp else 'Start SteamVR and connect Frame to the PC first.'
        raise SystemExit(f'Pose reader initialization failed: {exc}\n{hint}')
    # The FVR1 UDP packet carries poses only.
    fields = frozenset() if args.udp else config.fields
    tracker = None
    if config.relative_enabled:
        settle = 0.0 if args.save_preview or args.benchmark else config.settle_seconds
        tracker = RelativePoseTracker(config.relative_mode, settle)
    try:
        plt.rcParams['keymap.home'] = [k for k in plt.rcParams['keymap.home'] if k != 'r']
        fig = plt.figure(figsize=(15, 8))
        grid = fig.add_gridspec(2, 2, width_ratios=(1.2, 1), left=0.01, right=0.99,
                                top=0.93, bottom=0.07, wspace=0.04, hspace=0.06)
        ax = fig.add_subplot(grid[:, 0], projection='3d')
        # Plot coordinates (X, -Z, Y) so physical up is the vertical plot axis.
        P = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])
        if tracker and tracker.mode == 'own_frame':
            frame_label = 'rel (own frame)'
            labels = ('X, initial controller frame (m)', '-Z, initial controller frame (m)', 'Y, initial controller frame (m)')
        elif tracker:
            frame_label = 'rel (world axes)'
            labels = ('dX right (m)', 'd(-Z) forward (m)', 'dY up (m)')
        else:
            frame_label = 'absolute'
            labels = ('SteamVR X / right (m)', 'SteamVR -Z / forward (m)', 'SteamVR Y / up (m)')
        ax.set_xlabel(labels[0])
        ax.set_ylabel(labels[1])
        ax.set_zlabel(labels[2])
        ax.set_box_aspect((1, 1, 1))
        title = ax.set_title('')
        fast = fig.canvas.supports_blit and not args.full_redraw and not args.save_preview
        panels = {name: ControllerPanel(fig.add_subplot(grid[i, 1]), name, fields, fast)
                  for i, name in enumerate(('left', 'right'))}
        trails, artists = {}, {}
        centered = False
        if tracker:
            h = args.span / 2
            ax.set_xlim(-h, h)
            ax.set_ylim(-h, h)
            ax.set_zlim(-h, h)
            centered = True
        banner = fig.text(0.11, 0.0375, '', va='center', fontsize=10, animated=fast)
        # Two cached layers: the static figure, and static + text (refreshed at
        # TEXT_HZ because text rendering costs ~1 ms per artist).
        background = text_background = None
        last_text = -np.inf
        last_status = None
        force_redraw = False

        def reset_pose(_=None):
            nonlocal force_redraw
            if tracker:
                tracker.reset()
                for trail in trails.values():
                    trail.clear()
                force_redraw = True

        button = None
        if tracker:
            button = Button(fig.add_axes([0.01, 0.015, 0.09, 0.045]), 'Reset Pose')
            button.on_clicked(reset_pose)
            fig.canvas.mpl_connect('key_press_event', lambda e: e.key == 'r' and reset_pose())

        def moving_artists():
            return ([art for group in artists.values() for art in group]
                    + [art for panel in panels.values() for art in panel.shapes])

        def text_artists():
            return [banner] + [art for panel in panels.values() for art in panel.texts]

        def paint(now=None):
            nonlocal text_background, last_text
            if background is None:
                return
            if text_background is None or now is None or now - last_text >= 1 / TEXT_HZ:
                fig.canvas.restore_region(background)
                for art in text_artists():
                    fig.draw_artist(art)
                text_background = fig.canvas.copy_from_bbox(fig.bbox)
                last_text = time.monotonic() if now is None else now
            fig.canvas.restore_region(text_background)
            for art in moving_artists():
                if art.get_visible():
                    fig.draw_artist(art)
            fig.canvas.blit(fig.bbox)

        def on_draw(_):
            nonlocal background, text_background
            if fast:
                background = fig.canvas.copy_from_bbox(fig.bbox)
                text_background = None
                paint()

        fig.canvas.mpl_connect('draw_event', on_draw)

        def update(_):
            nonlocal centered, last_status, force_redraw
            redraw, force_redraw = force_redraw, False
            poses = reader.read()
            now = time.monotonic()
            shown = tracker.apply(poses, now) if tracker else poses
            if shown and not centered:
                center = np.mean([P @ p.T[:3, 3] for p in shown.values()], axis=0)
                h = args.span / 2
                ax.set_xlim(center[0]-h, center[0]+h)
                ax.set_ylim(center[1]-h, center[1]+h)
                ax.set_zlim(center[2]-h, center[2]+h)
                centered = True
                redraw = True
            for name in artists.keys() - shown.keys():
                for art in artists[name]:
                    art.set_visible(False)
                trails[name].clear()  # don't connect a trail across lost tracking
            for name, pose in shown.items():
                if name not in artists:
                    color = COLORS.get(name, 'gray')
                    trail, = ax.plot([], [], [], color=color, alpha=0.5)
                    marker, = ax.plot([], [], [], 'o', color=color, label=name)
                    axes = [ax.plot([], [], [], color=c, lw=2)[0] for c in ('r', 'g', 'b')]
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
            for name, panel in panels.items():
                panel.update(poses.get(name), shown.get(name), frame_label)
            if tracker and tracker.remaining(now) > 0:
                banner.set_text(f'Capturing reference in {tracker.remaining(now):.1f} s: hold controllers still')
            elif tracker:
                banner.set_text(f'Relative pose ({tracker.mode}): Reset Pose button or R key recaptures')
            else:
                banner.set_text('Absolute pose (relative_pose.enabled = false in config.toml)')
            status = ', '.join(sorted(poses)) or 'NONE: check tracking/connection'
            if status != last_status:
                label = 'SYNTHETIC DEMO' if args.demo else 'Live Frame UDP poses' if args.udp else 'Live SteamVR poses'
                title.set_text(f'{label}\nTracked: {status} | local axes: X red, Y green, Z blue')
                last_status = status
                redraw = True
            if fast and background is not None and not redraw:
                paint(now)
            else:
                fig.canvas.draw()

        if args.save_preview:
            update(0)
            fig.savefig(args.save_preview, dpi=110, bbox_inches='tight')
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
