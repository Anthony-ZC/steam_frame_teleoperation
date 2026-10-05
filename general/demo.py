"""Synthetic controller states for hardware-free tests; stdlib only so the Frame sender can use it."""
import math
from general.controller_state import BUTTONS, ButtonState, ControllerState


def demo_states(t, fields):
    """Two controllers circling in front of the user, with inputs for the enabled field groups."""
    result = {}
    for i, name in enumerate(('left', 'right')):
        a = t + i * math.pi
        c, s = math.cos(a), math.sin(a)
        matrix = [c, 0.0, s, (-0.3 if i == 0 else 0.3) + 0.12*c,
                  0.0, 1.0, 0.0, 1.2 + 0.08*math.sin(2*a),
                  -s, 0.0, c, -0.4 + 0.12*s]
        state = ControllerState(name, i, matrix, 200)
        if 'velocity' in fields:
            state.velocity = (-0.12*s, 0.16*math.cos(2*a), 0.12*c)
            state.angular_velocity = (0.0, 1.0, 0.0)
        if 'battery' in fields:
            state.battery = max(0.0, 0.9 - 0.001*t)
            state.charging = False
            state.controller_type = 'demo'
        curl = tuple(0.5 + 0.5*math.sin(0.8*t + 0.7*f + i) for f in range(5))
        if 'fingers' in fields:
            state.finger_curl = curl
            state.finger_splay = tuple(0.5 + 0.5*math.sin(0.5*t + g) for g in range(4))
            state.skeletal_level = 1
        if 'analog' in fields:
            state.trigger, state.grip = curl[1], curl[2]
            state.thumbstick = (math.cos(1.3*t) * 0.8, math.sin(1.3*t) * 0.8)
        if 'buttons' in fields:
            phase = int(t) % 4  # cycle the thumb over the face buttons
            touch = {b: False for b in BUTTONS}
            touch.update({'abxy'[phase]: curl[0] > 0.6, 'thumbrest': curl[0] < 0.3,
                          'thumbstick': 0.3 <= curl[0] <= 0.6, 'trigger': curl[1] > 0.3,
                          'bumper': 0.15 < curl[1] < 0.3, 'grip': curl[2] > 0.3})
            press = {b: False for b in BUTTONS}
            press.update({'abxy'[phase]: curl[0] > 0.9, 'trigger': curl[1] > 0.85, 'grip': curl[2] > 0.85})
            state.buttons = {b: ButtonState(press[b], touch[b] or press[b]) for b in BUTTONS}
        if set(fields) & {'buttons', 'analog', 'fingers'}:
            state.input_source = 'demo'
        result[name] = state
    return result
