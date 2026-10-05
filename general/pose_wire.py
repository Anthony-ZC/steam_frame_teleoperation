"""Compact, versioned UDP snapshots; stdlib only for the headset sender.

FVR1 (poses only) header: version, standing-space flag, count, session ID,
sequence, sender monotonic ns. Each entry: device ID, role, reserved, tracking
result, then twelve float32 values of the row-major device-to-standing 3x4 matrix.

FVR2 adds a group bitmask to the header (count becomes one byte). Each entry has
the FVR1 layout (the reserved byte carries the input source), followed by one
block per group present, in GROUP_BITS order:
  velocity 6f (linear, angular) | battery fB (level, charging)
  buttons HHH (has-data, pressed, touched bitmasks over BUTTONS)
  analog 4f (trigger, grip, stick x, y) | fingers 9fB (curl x5, splay x4, level)
NaN floats and 255 bytes mean "no data". Sender time is diagnostic only: clocks
on the two machines are not synced.
"""
import math
import struct
from general.controller_state import BUTTONS, ButtonState, ControllerState

HEADER = struct.Struct('!4sBBHQQQ')
HEADER2 = struct.Struct('!4sBBBBQQQ')
ENTRY = struct.Struct('!HBBI12f')
GROUP_BITS = {'velocity': 1, 'battery': 2, 'buttons': 4, 'analog': 8, 'fingers': 16}
BLOCKS = {'velocity': struct.Struct('!6f'), 'battery': struct.Struct('!fB'),
          'buttons': struct.Struct('!HHH'), 'analog': struct.Struct('!4f'),
          'fingers': struct.Struct('!9fB')}
SOURCES = (None, 'actions', 'legacy', 'actions+legacy', 'demo')
ROLES = {'left': 1, 'right': 2}
MAX_CONTROLLERS = 8
MAX_PACKET = HEADER2.size + MAX_CONTROLLERS * (ENTRY.size + sum(b.size for b in BLOCKS.values()))
NAN = float('nan')


def encode(session, sequence, sender_ns, entries):
    """FVR1: entries are (device, role, tracking, matrix) tuples."""
    if len(entries) > MAX_CONTROLLERS:
        raise ValueError('too many controllers')
    payload = HEADER.pack(b'FVR1', 1, 1, len(entries), session, sequence, sender_ns)
    for device, role, tracking, matrix in entries:
        payload += ENTRY.pack(device, role, 0, tracking, *matrix)
    # Use the same validation on both sides.
    decode(payload)
    return payload


def _floats(values, size):
    return tuple(NAN if v is None else float(v) for v in values) if values else (NAN,) * size


def _pack_block(group, s):
    if group == 'velocity':
        return BLOCKS[group].pack(*_floats(s.velocity, 3), *_floats(s.angular_velocity, 3))
    if group == 'battery':
        return BLOCKS[group].pack(NAN if s.battery is None else s.battery,
                                  255 if s.charging is None else int(bool(s.charging)))
    if group == 'buttons':
        masks = [0, 0, 0]
        for bit, name in enumerate(BUTTONS):
            state = (s.buttons or {}).get(name)
            if state:
                masks[0] |= 1 << bit
                masks[1] |= int(bool(state.pressed)) << bit
                masks[2] |= int(bool(state.touched)) << bit
        return BLOCKS[group].pack(*masks)
    if group == 'analog':
        return BLOCKS[group].pack(*_floats((s.trigger, s.grip), 2), *_floats(s.thumbstick, 2))
    level = 255 if s.skeletal_level is None else s.skeletal_level
    return BLOCKS[group].pack(*_floats(s.finger_curl, 5), *_floats(s.finger_splay, 4), level)


def encode_states(session, sequence, sender_ns, states, groups=()):
    """FVR2: ControllerStates plus the requested field groups."""
    if len(states) > MAX_CONTROLLERS:
        raise ValueError('too many controllers')
    groups = [g for g in GROUP_BITS if g in groups]
    mask = sum(GROUP_BITS[g] for g in groups)
    parts = [HEADER2.pack(b'FVR2', 2, 1, len(states), mask, session, sequence, sender_ns)]
    for s in states:
        source = SOURCES.index(s.input_source) if s.input_source in SOURCES else 0
        parts.append(ENTRY.pack(s.device_id, ROLES.get(s.name, 0), source, s.tracking_result, *s.matrix))
        parts += [_pack_block(g, s) for g in groups]
    payload = b''.join(parts)
    decode(payload)
    return payload


def _optional(values):
    """All-NaN -> None; any infinity or partial NaN is malformed."""
    if all(math.isnan(v) for v in values):
        return None
    if not all(map(math.isfinite, values)):
        raise ValueError('invalid controller entry')
    return tuple(values)


def _unpack_block(group, values, s):
    if group == 'velocity':
        s.velocity, s.angular_velocity = _optional(values[:3]), _optional(values[3:])
    elif group == 'battery':
        level, charging = values
        s.battery = None if _optional((level,)) is None else level
        if charging not in (0, 1, 255):
            raise ValueError('invalid controller entry')
        s.charging = None if charging == 255 else bool(charging)
    elif group == 'buttons':
        has, pressed, touched = values
        s.buttons = {name: ButtonState(bool(pressed >> bit & 1), bool(touched >> bit & 1))
                     for bit, name in enumerate(BUTTONS) if has >> bit & 1}
    elif group == 'analog':
        trigger, grip = (_optional((v,)) for v in values[:2])
        s.trigger = trigger and trigger[0]
        s.grip = grip and grip[0]
        s.thumbstick = _optional(values[2:])
    else:
        s.finger_curl, s.finger_splay = _optional(values[:5]), _optional(values[5:9])
        s.skeletal_level = None if values[9] == 255 else values[9]


def decode(payload):
    """Return (session, sequence, sender_ns, groups, [ControllerState]) for FVR1 or FVR2."""
    if len(payload) < HEADER.size:
        raise ValueError('short header')
    if payload[:4] == b'FVR1':
        magic, version, space, count, session, sequence, sender_ns = HEADER.unpack_from(payload)
        mask = 0
    else:
        magic, version, space, count, mask, session, sequence, sender_ns = HEADER2.unpack_from(payload)
    if ((magic, version) not in ((b'FVR1', 1), (b'FVR2', 2)) or space != 1
            or count > MAX_CONTROLLERS or mask & ~sum(GROUP_BITS.values())):
        raise ValueError('unsupported packet')
    groups = [g for g, bit in GROUP_BITS.items() if mask & bit]
    entry_size = ENTRY.size + sum(BLOCKS[g].size for g in groups)
    if len(payload) != HEADER.size + count * entry_size:
        raise ValueError('wrong packet length')
    states, devices, roles = [], set(), set()
    offset = HEADER.size
    for _ in range(count):
        device, role, source, tracking, *matrix = ENTRY.unpack_from(payload, offset)
        offset += ENTRY.size
        if (device >= 64 or device in devices or role not in (0, 1, 2)
                or (source if magic == b'FVR1' else source >= len(SOURCES))
                or tracking != 200 or not all(map(math.isfinite, matrix))):
            raise ValueError('invalid controller entry')
        if role and role in roles:
            raise ValueError('duplicate controller role')
        devices.add(device)
        roles.add(role)
        name = {1: 'left', 2: 'right'}.get(role, f'device_{device}')
        state = ControllerState(name, device, matrix, tracking, input_source=SOURCES[source])
        for group in groups:
            _unpack_block(group, BLOCKS[group].unpack_from(payload, offset), state)
            offset += BLOCKS[group].size
        states.append(state)
    return session, sequence, sender_ns, frozenset(groups), states
