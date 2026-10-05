"""Reader interface shared by SteamVR, UDP and demo sources, plus the demo reader."""
import time
from general.config import FIELD_GROUPS
from general.demo import demo_states
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
        return {name: pose_from_state(state, now)
                for name, state in demo_states(now - self.started, self.fields).items()}
