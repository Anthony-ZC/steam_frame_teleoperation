"""Reader interface shared by SteamVR, UDP and demo sources, plus the demo reader."""
import math
import time
import numpy as np
from general.config import FIELD_GROUPS
from general.controller_state import BUTTONS, ButtonState, ControllerState
from general.poses import pose_from_state


class ControllerReader:
    """read() returns {name: Pose} for currently tracked controllers ('left', 'right', ...)."""
    def read(self):
        raise NotImplementedError

    def close(self):
        pass


class DemoReader(ControllerReader):
    """Synthetic trajectories and inputs solely for checking scripts without VR hardware."""
    def __init__(self, fields=FIELD_GROUPS):
        self.fields = frozenset(fields)
        self.started = time.monotonic()

    def read(self):
        now = time.monotonic()
        t = now - self.started
        result = {}
        for i, name in enumerate(('left', 'right')):
            a = t + i * np.pi
            c, s = np.cos(a), np.sin(a)
            matrix = [c, 0, s, (-0.3 if i == 0 else 0.3) + 0.12*c,
                      0, 1, 0, 1.2 + 0.08*np.sin(2*a),
                      -s, 0, c, -0.4 + 0.12*s]
            state = ControllerState(name, i, [float(v) for v in matrix], 200)
            if 'velocity' in self.fields:
                state.velocity = (-0.12*s, 0.16*np.cos(2*a), 0.12*c)
                state.angular_velocity = (0.0, 1.0, 0.0)
            if 'battery' in self.fields:
                state.battery = max(0.0, 0.9 - 0.001*t)
                state.charging = False
                state.controller_type = 'demo'
            curl = tuple(0.5 + 0.5*math.sin(0.8*t + 0.7*f + i) for f in range(5))
            if 'fingers' in self.fields:
                state.finger_curl = curl
                state.finger_splay = tuple(0.5 + 0.5*math.sin(0.5*t + g) for g in range(4))
                state.skeletal_level = 1
            if 'analog' in self.fields:
                state.trigger, state.grip = curl[1], curl[2]
                state.thumbstick = (math.cos(1.3*t) * 0.8, math.sin(1.3*t) * 0.8)
            if 'buttons' in self.fields:
                phase = int(t) % 4  # cycle the thumb over the face buttons
                thumb_on = curl[0] > 0.6
                touch = {b: False for b in BUTTONS}
                touch.update({'abxy'[phase]: thumb_on, 'thumbrest': curl[0] < 0.3,
                              'thumbstick': 0.3 <= curl[0] <= 0.6, 'trigger': curl[1] > 0.3,
                              'bumper': 0.15 < curl[1] < 0.3, 'grip': curl[2] > 0.3})
                press = {b: False for b in BUTTONS}
                press.update({'abxy'[phase]: curl[0] > 0.9, 'trigger': curl[1] > 0.85, 'grip': curl[2] > 0.85})
                state.buttons = {b: ButtonState(press[b], touch[b] or press[b]) for b in BUTTONS}
            if self.fields & {'buttons', 'analog', 'fingers'}:
                state.input_source = 'demo'
            result[name] = pose_from_state(state, now)
        return result
