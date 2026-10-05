"""Read controller poses and inputs through OpenVR; numpy-free so Frame can run it too.

Poses and velocities come from IVRSystem. Buttons, analog values and finger curl
come from SteamVR Input (IVRInput) using general/input/actions.json. When an
input group is inactive (no binding, no focus), the deprecated legacy controller
state fills buttons and analog values; finger curl has no legacy equivalent.
"""
import platform
import sys
import time
from pathlib import Path
from general.config import INPUT_GROUPS
from general.controller_state import BUTTONS, TOUCH_ONLY, ButtonState, ControllerState

MANIFEST = Path(__file__).resolve().parent / 'input' / 'actions.json'
VENDOR = Path(__file__).resolve().parent.parent / 'non_pc_streaming' / 'vendor'
ACTION_SET = '/actions/teleop'
HANDS = {1: 'left', 2: 'right'}  # TrackedControllerRole_LeftHand / RightHand
BUTTON_ACTIONS = tuple((b, kind) for b in BUTTONS
                       for kind in (('touch',) if b in TOUCH_ONLY else ('click', 'touch')))
APP_TYPES = {'background': 'VRApplication_Background', 'overlay': 'VRApplication_Overlay',
             'scene': 'VRApplication_Scene'}

# Legacy EVRButtonId bits and rAxis indices. The layout depends on the legacy
# binding SteamVR applies per controller type; probe_controller prints raw bits
# so a Frame entry can be added here.
LEGACY_LAYOUTS = {
    'default': {'buttons': {'system': 0, 'b': 1, 'grip': 2, 'a': 7, 'thumbstick': 32, 'trigger': 33},
                'axes': {'thumbstick': 0, 'trigger': 1, 'grip': 2}},
    'knuckles': {'buttons': {'system': 0, 'b': 1, 'a': 2, 'thumbstick': 35, 'trigger': 33, 'grip': 34},
                 'axes': {'thumbstick': 3, 'trigger': 1, 'grip': 2}},
}


def load_openvr():
    """Import pyopenvr; on Frame (Linux ARM64) use the bundled ARM64 copy."""
    if platform.system() == 'Linux' and platform.machine().lower() in ('aarch64', 'arm64'):
        sys.path.insert(0, str(VENDOR))
    import openvr
    return openvr


def runtime_report():
    """Lines describing how libopenvr_api will find the runtime, for failed-init diagnosis."""
    import json
    import os
    lines = [f'Python {platform.python_version()} on {platform.system()} {platform.machine()}']
    if platform.system() == 'Windows':
        vrpath = Path(os.environ.get('LOCALAPPDATA', '')) / 'openvr' / 'openvrpaths.vrpath'
    else:
        vrpath = Path.home() / '.config' / 'openvr' / 'openvrpaths.vrpath'
    try:
        paths = json.loads(vrpath.read_text(encoding='utf-8'))
        lines.append(f'Runtime registry {vrpath}:')
        for key in ('runtime', 'config'):
            lines.append(f'  {key}: {", ".join(paths.get(key) or []) or "-"}')
    except FileNotFoundError:
        lines.append(f'Runtime registry {vrpath}: MISSING (OpenVR cannot locate a runtime)')
    except (OSError, ValueError) as exc:
        lines.append(f'Runtime registry {vrpath}: unreadable ({exc})')
    proc = Path('/proc')
    if proc.is_dir():
        names = set()
        for comm in proc.glob('[0-9]*/comm'):
            try:
                name = comm.read_text().strip()
            except OSError:
                continue
            if name.startswith('vr') or 'steam' in name.lower():
                names.add(name)
        lines.append(f'VR/Steam processes: {", ".join(sorted(names)) or "none (a background app needs vrserver)"}')
    return lines


def init_openvr(vr, app_type='background'):
    return vr.init(getattr(vr, APP_TYPES[app_type]))


def decode_legacy(pressed, touched, axes, controller_type=None):
    """Map a legacy VRControllerState_t (bitmasks, [(x, y)] * 5) to named inputs."""
    layout = LEGACY_LAYOUTS.get(controller_type, LEGACY_LAYOUTS['default'])
    buttons = {name: ButtonState(bool(pressed >> bit & 1), bool(touched >> bit & 1))
               for name, bit in layout['buttons'].items()}
    index = layout['axes']
    return {'buttons': buttons, 'trigger': axes[index['trigger']][0],
            'grip': axes[index['grip']][0], 'thumbstick': tuple(axes[index['thumbstick']])}


def _value(result):
    return int(getattr(result, 'value', result))


class ActionInput:
    """SteamVR Input actions for both hands; created only when an input group is enabled."""
    def __init__(self, vr, fields):
        self.vr, self.fields = vr, fields
        self.api = vr.VRInput()
        # Must precede the first UpdateActionState / PollNextEvent.
        self.api.setActionManifestPath(str(MANIFEST))
        # pyopenvr's updateActionState needs a ctypes array, not a single struct.
        self.sets = (vr.VRActiveActionSet_t * 1)()
        self.sets[0].ulActionSet = self.api.getActionSetHandle(ACTION_SET)
        action = lambda name: self.api.getActionHandle(f'{ACTION_SET}/in/{name}')
        self.digital = {f'{b}_{kind}': action(f'{b}_{kind}') for b, kind in BUTTON_ACTIONS}
        self.analog = {name: action(name) for name in ('trigger', 'grip', 'thumbstick')}
        self.skeleton = {hand: action(f'skeleton_{hand}') for hand in HANDS.values()}
        self.sources = {hand: self.api.getInputSourceHandle(f'/user/hand/{hand}')
                        for hand in HANDS.values()}

    def update(self):
        self.api.updateActionState(self.sets)

    def read(self, hand):
        """Return {group: values} for the active groups of one hand."""
        api, source, result = self.api, self.sources[hand], {}
        if 'buttons' in self.fields:
            data = {k: api.getDigitalActionData(h, source) for k, h in self.digital.items()}
            if any(d.bActive for d in data.values()):
                # Unbound controls (e.g. no X/Y on Index) stay inactive and are left out.
                active = lambda key: key in data and bool(data[key].bActive)
                on = lambda key: active(key) and bool(data[key].bState)
                result['buttons'] = {b: ButtonState(on(f'{b}_click'), on(f'{b}_touch'))
                                     for b in BUTTONS if active(f'{b}_click') or active(f'{b}_touch')}
        if 'analog' in self.fields:
            data = {k: api.getAnalogActionData(h, source) for k, h in self.analog.items()}
            if any(d.bActive for d in data.values()):
                result['trigger'] = data['trigger'].x
                result['grip'] = data['grip'].x
                result['thumbstick'] = (data['thumbstick'].x, data['thumbstick'].y)
        if 'fingers' in self.fields:
            handle = self.skeleton[hand]
            if api.getSkeletalActionData(handle).bActive:
                summary = api.getSkeletalSummaryData(handle, self.vr.VRSummaryType_FromDevice)
                result['finger_curl'] = tuple(summary.flFingerCurl)
                result['finger_splay'] = tuple(summary.flFingerSplay)
                result['skeletal_level'] = _value(api.getSkeletalTrackingLevel(handle))
        return result


class OpenVRSampler:
    def __init__(self, vr, system, fields=(), legacy_fallback=True, max_controllers=8):
        self.vr, self.system = vr, system
        self.fields = frozenset(fields)
        self.legacy_fallback = legacy_fallback
        self.max_controllers = max_controllers
        self.buffer = (vr.TrackedDevicePose_t * vr.k_unMaxTrackedDeviceCount)()
        self.event = vr.VREvent_t()
        self.properties = {}  # device -> (refresh time, values)
        self.quit_requested = False
        # While the SteamVR dashboard is open it receives all controller input, and
        # other apps' actions turn inactive. Checked about once per second.
        self.dashboard_visible = False
        self._dashboard_checked = 0.0
        self.input = self.input_error = None
        if self.fields & INPUT_GROUPS:
            try:
                self.input = ActionInput(vr, self.fields)
            except Exception as exc:  # missing runtime support, bad manifest...
                self.input_error = f'{type(exc).__name__}: {exc}'

    def sample(self):
        """Return {name: ControllerState} for fully tracked controllers."""
        vr, system = self.vr, self.system
        while system.pollNextEvent(self.event):
            if self.event.eventType == vr.VREvent_Quit:
                system.acknowledgeQuit_Exiting()
                self.quit_requested = True
        system.getDeviceToAbsoluteTrackingPose(vr.TrackingUniverseStanding, 0, self.buffer)
        if self.input:
            try:
                self.input.update()
            except Exception as exc:
                self.input_error = f'{type(exc).__name__}: {exc}'
                self.input = None
            now = time.monotonic()
            if now - self._dashboard_checked >= 1.0:
                self._dashboard_checked = now
                try:
                    self.dashboard_visible = bool(vr.VROverlay().isDashboardVisible())
                except Exception:
                    self.dashboard_visible = False
        result, roles = {}, set()
        for device, pose in enumerate(self.buffer):
            if (system.getTrackedDeviceClass(device) != vr.TrackedDeviceClass_Controller
                    or not pose.bDeviceIsConnected or not pose.bPoseIsValid
                    or pose.eTrackingResult != vr.TrackingResult_Running_OK):
                continue
            role = int(system.getControllerRoleForTrackedDeviceIndex(device))
            name = HANDS[role] if role in HANDS and role not in roles else f'device_{device}'
            roles.add(role)
            matrix = [pose.mDeviceToAbsoluteTracking.m[r][c] for r in range(3) for c in range(4)]
            state = ControllerState(name, device, matrix, int(pose.eTrackingResult))
            if 'velocity' in self.fields:
                state.velocity = tuple(pose.vVelocity.v)
                state.angular_velocity = tuple(pose.vAngularVelocity.v)
            if 'battery' in self.fields or self.fields & INPUT_GROUPS:
                props = self._properties(device)
                state.controller_type = props['controller_type']
                if 'battery' in self.fields:
                    state.battery, state.charging = props['battery'], props['charging']
            if self.fields & INPUT_GROUPS:
                self._read_input(device, state)
            result[name] = state
            if len(result) == self.max_controllers:
                break
        return result

    def _properties(self, device):
        now = time.monotonic()
        cached = self.properties.get(device)
        if cached and now - cached[0] < 1.0:
            return cached[1]
        system, vr = self.system, self.vr

        def get(getter, prop):
            try:
                return getter(device, prop)
            except Exception:  # property not provided by this driver
                return None
        values = {'battery': get(system.getFloatTrackedDeviceProperty, vr.Prop_DeviceBatteryPercentage_Float),
                  'charging': get(system.getBoolTrackedDeviceProperty, vr.Prop_DeviceIsCharging_Bool),
                  'controller_type': cached[1]['controller_type'] if cached else
                  get(system.getStringTrackedDeviceProperty, vr.Prop_ControllerType_String)}
        self.properties[device] = (now, values)
        return values

    def _read_input(self, device, state):
        values, sources = {}, []
        if self.input and state.name in HANDS.values():
            try:
                values = self.input.read(state.name)
            except Exception as exc:
                self.input_error = f'{type(exc).__name__}: {exc}'
            if values:
                sources.append('actions')
        found = {'buttons'} if 'buttons' in values else set()
        if 'trigger' in values:
            found.add('analog')
        missing = {g for g in ('buttons', 'analog') if g in self.fields} - found
        if missing and self.legacy_fallback:
            ok, raw = self.system.getControllerState(device)
            if ok:
                legacy = decode_legacy(raw.ulButtonPressed, raw.ulButtonTouched,
                                       [(a.x, a.y) for a in raw.rAxis], state.controller_type)
                if 'buttons' in missing:
                    values['buttons'] = legacy['buttons']
                if 'analog' in missing:
                    values.update(trigger=legacy['trigger'], grip=legacy['grip'],
                                  thumbstick=legacy['thumbstick'])
                sources.append('legacy')
        for key, value in values.items():
            setattr(state, key, value)
        state.input_source = '+'.join(sources) or None
