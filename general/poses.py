"""Shared pose model (PC side, numpy)."""
from dataclasses import dataclass
from typing import Optional
import numpy as np
from general.controller_state import ControllerState


@dataclass
class Pose:
    name: str
    device_id: int
    T: np.ndarray  # device-local -> SteamVR standing space
    received_monotonic: float  # host receipt time, NOT sensor capture time
    tracking_result: int
    velocity: Optional[np.ndarray] = None          # m/s, same frame as T
    angular_velocity: Optional[np.ndarray] = None  # rad/s, same frame as T
    state: Optional[ControllerState] = None        # buttons, fingers, battery...


def pose_from_state(state, received):
    T = np.eye(4)
    T[:3, :] = np.array(state.matrix, dtype=float).reshape(3, 4)
    velocity = None if state.velocity is None else np.array(state.velocity, dtype=float)
    angular = None if state.angular_velocity is None else np.array(state.angular_velocity, dtype=float)
    return Pose(state.name, state.device_id, T, received, state.tracking_result,
                velocity, angular, state)
