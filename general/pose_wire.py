"""Compact, versioned UDP snapshots; stdlib only for the headset sender.

FVR1 header: version, standing-space flag, count, session ID, sequence,
sender monotonic ns. Each entry: device ID, role, reserved, tracking result,
then twelve float32 values of the row-major device-to-standing 3x4 matrix.
Sender time is diagnostic only: clocks on the two machines are not synced.
"""
import math
import struct

HEADER = struct.Struct('!4sBBHQQQ')
ENTRY = struct.Struct('!HBBI12f')
MAX_CONTROLLERS = 8
MAX_PACKET = HEADER.size + ENTRY.size * MAX_CONTROLLERS


def encode(session, sequence, sender_ns, entries):
    if len(entries) > MAX_CONTROLLERS:
        raise ValueError('too many controllers')
    payload = HEADER.pack(b'FVR1', 1, 1, len(entries), session, sequence, sender_ns)
    for device, role, tracking, matrix in entries:
        payload += ENTRY.pack(device, role, 0, tracking, *matrix)
    # Use the same validation on both sides.
    decode(payload)
    return payload


def decode(payload):
    if len(payload) < HEADER.size:
        raise ValueError('short header')
    magic, version, space, count, session, sequence, sender_ns = HEADER.unpack_from(payload)
    if magic != b'FVR1' or version != 1 or space != 1 or count > MAX_CONTROLLERS:
        raise ValueError('unsupported packet')
    if len(payload) != HEADER.size + count * ENTRY.size:
        raise ValueError('wrong packet length')
    entries, devices, roles = [], set(), set()
    for index in range(count):
        fields = ENTRY.unpack_from(payload, HEADER.size + index * ENTRY.size)
        device, role, reserved, tracking, *matrix = fields
        if (device >= 64 or device in devices or role not in (0, 1, 2)
                or reserved or tracking != 200 or not all(map(math.isfinite, matrix))):
            raise ValueError('invalid controller entry')
        if role and role in roles:
            raise ValueError('duplicate controller role')
        devices.add(device)
        roles.add(role)
        entries.append((device, role, tracking, matrix))
    return session, sequence, sender_ns, entries
