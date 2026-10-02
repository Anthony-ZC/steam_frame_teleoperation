"""Shared pose model and hardware-free synthetic trajectories."""
from dataclasses import dataclass
import time
import numpy as np


@dataclass
class Pose:
    name: str
    device_id: int
    T: np.ndarray  # device-local -> SteamVR standing space
    received_monotonic: float  # host receipt time, NOT sensor capture time
    tracking_result: int


class DemoReader:
    """Synthetic trajectories solely for checking scripts without VR hardware."""
    def __init__(self):
        self.started = time.monotonic()

    def read(self):
        now = time.monotonic()
        t = now - self.started
        result = {}
        for i, name in enumerate(('left', 'right')):
            a = t + i * np.pi
            c, s = np.cos(a), np.sin(a)
            T = np.eye(4)
            T[:3, :3] = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
            T[:3, 3] = [(-0.3 if i == 0 else 0.3) + 0.12*c,
                          1.2 + 0.08*np.sin(2*a), -0.4 + 0.12*s]
            result[name] = Pose(name, i, T, now, 200)
        return result

    def close(self):
        pass
