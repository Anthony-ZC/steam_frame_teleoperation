"""List what each controller exposes: properties, legacy state, SteamVR Input, fingers.

Touch, press and squeeze every control while it runs; it prints changes live and
ends with a per-field summary. Numpy-free: runs on the PC (SteamVR streaming)
or on Frame itself (`python3 -m general.probe_controller`).
"""
import argparse
import time
from general import config as config_file
from general.config import FIELD_GROUPS
from general.openvr_sampler import LEGACY_LAYOUTS, OpenVRSampler, init_openvr, load_openvr

PROPERTIES = (('model', 'String', 'Prop_ModelNumber_String'),
              ('manufacturer', 'String', 'Prop_ManufacturerName_String'),
              ('serial', 'String', 'Prop_SerialNumber_String'),
              ('controller_type', 'String', 'Prop_ControllerType_String'),
              ('input_profile', 'String', 'Prop_InputProfilePath_String'),
              ('render_model', 'String', 'Prop_RenderModelName_String'),
              ('battery', 'Float', 'Prop_DeviceBatteryPercentage_Float'),
              ('charging', 'Bool', 'Prop_DeviceIsCharging_Bool'),
              *((f'axis{i}_type', 'Int32', f'Prop_Axis{i}Type_Int32') for i in range(5)))
AXIS_TYPES = {0: 'none', 1: 'trackpad', 2: 'joystick', 3: 'trigger'}
BIT_NAMES = {0: 'System', 1: 'ApplicationMenu', 2: 'Grip', 3: 'DPad_Left', 4: 'DPad_Up',
             5: 'DPad_Right', 6: 'DPad_Down', 7: 'A', 31: 'ProximitySensor',
             32: 'Axis0', 33: 'Axis1', 34: 'Axis2', 35: 'Axis3', 36: 'Axis4'}
GROUP_KEYS = {'velocity': ('velocity', 'angular_velocity'), 'battery': ('battery', 'charging'),
              'buttons': ('buttons',), 'analog': ('trigger', 'grip', 'thumbstick'),
              'fingers': ('finger_curl', 'finger_splay', 'skeletal_level')}


def bits(mask):
    return [BIT_NAMES.get(b, f'bit{b}') for b in range(64) if mask >> b & 1]


def rounded(value):
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, (tuple, list)):
        return tuple(rounded(v) for v in value)
    if isinstance(value, dict):
        return {k: (v.pressed, v.touched) for k, v in value.items()}
    return value


def properties(vr, system, device):
    values = {}
    for name, kind, prop in PROPERTIES:
        try:
            value = getattr(system, f'get{kind}TrackedDeviceProperty')(device, getattr(vr, prop))
        except Exception as exc:
            value = f'<{type(exc).__name__}>'
        if name.startswith('axis') and isinstance(value, int):
            value = f'{value} ({AXIS_TYPES.get(value, "?")})'
        values[name] = value
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--hz', type=float, default=60)
    parser.add_argument('--app-type', choices=('background', 'overlay', 'scene'),
                        help='Override input.app_type from config.toml')
    parser.add_argument('--config', help='config.toml path')
    args = parser.parse_args()
    config = config_file.load(args.config)
    vr = load_openvr()
    try:
        system = init_openvr(vr, args.app_type or config.app_type)
    except Exception as exc:
        raise SystemExit(f'OpenVR initialization failed: {exc}\nStart SteamVR and connect Frame first.')
    try:
        # Actions only (no legacy fallback) so the two input paths are reported separately.
        sampler = OpenVRSampler(vr, system, FIELD_GROUPS, legacy_fallback=False)
        print(f'App type: {args.app_type or config.app_type}')
        print(f'SteamVR Input: {"OK" if sampler.input else "UNAVAILABLE: " + str(sampler.input_error)}')
        print(f'Known legacy layouts: {", ".join(LEGACY_LAYOUTS)}\n')
        devices = [d for d in range(vr.k_unMaxTrackedDeviceCount)
                   if system.getTrackedDeviceClass(d) == vr.TrackedDeviceClass_Controller]
        if not devices:
            print('No controllers known to the runtime. Wake them and keep them in view.')
        for device in devices:
            role = int(system.getControllerRoleForTrackedDeviceIndex(device))
            print(f'Device {device} (role {role}, connected={system.isTrackedDeviceConnected(device)})')
            for name, value in properties(vr, system, device).items():
                print(f'  {name:16} {value}')
        print(f'\nTouch, press and move every control and finger for {args.seconds:g} s...\n')
        legacy_last, legacy_seen, legacy_axes = {}, {}, {}
        action_last, changed, present, speed = {}, {}, {}, {}
        start = time.monotonic()
        while time.monotonic() - start < args.seconds:
            t = time.monotonic() - start
            for device in devices:
                ok, raw = system.getControllerState(device)
                if not ok:
                    continue
                state = (raw.ulButtonPressed, raw.ulButtonTouched,
                         tuple((round(a.x, 1), round(a.y, 1)) for a in raw.rAxis))
                if device in legacy_last and state != legacy_last[device]:
                    print(f'{t:5.1f}s legacy dev{device}: pressed={bits(state[0])} '
                          f'touched={bits(state[1])} axes={state[2]}')
                seen = legacy_seen.setdefault(device, [0, 0])
                seen[0] |= state[0]
                seen[1] |= state[1]
                axes = legacy_axes.setdefault(device, set())
                axes.update(i for i, a in enumerate(state[2]) if a != (0.0, 0.0))
                legacy_last[device] = state
            for name, s in sampler.sample().items():
                if s.velocity:
                    v = sum(x*x for x in s.velocity) ** 0.5
                    speed[name] = max(speed.get(name, 0), v)
                for group, keys in GROUP_KEYS.items():
                    for key in keys:
                        value = rounded(getattr(s, key))
                        if value is None:
                            continue
                        present.setdefault(name, set()).add(group)
                        previous = action_last.get((name, key))
                        if previous is not None and value != previous:
                            changed.setdefault(name, set()).add(group)
                            if group in ('buttons', 'analog', 'fingers'):
                                print(f'{t:5.1f}s actions {name}.{key} = {value}')
                        action_last[(name, key)] = value
            time.sleep(1 / args.hz)
        print('\n=== Summary ===')
        for device, (pressed, touched) in legacy_seen.items():
            print(f'legacy dev{device}: pressed bits seen {bits(pressed) or "-"}; '
                  f'touched bits seen {bits(touched) or "-"}; active axes {sorted(legacy_axes[device]) or "-"}')
        for name in sorted(present.keys() | set(speed)):
            print(f'{name}:')
            for group in FIELD_GROUPS:
                if group not in present.get(name, ()):
                    status = 'UNAVAILABLE'
                else:
                    status = 'changed' if group in changed.get(name, ()) else 'present, never changed'
                extra = f' (max speed {speed[name]:.2f} m/s)' if group == 'velocity' and name in speed else ''
                print(f'  {group:9} {status}{extra}')
        if not present:
            print('No tracked controllers sampled.')
    finally:
        vr.shutdown()


if __name__ == '__main__':
    main()
