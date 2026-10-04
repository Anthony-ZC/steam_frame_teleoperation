"""Report poses relative to a reference captured after a settle delay."""
import dataclasses
import math
import time
import numpy as np


def euler_yxz_deg(R):
    """(roll, pitch, yaw) in degrees for R = Ry(yaw) Rx(pitch) Rz(roll), SteamVR axes."""
    pitch = math.asin(max(-1.0, min(1.0, -R[1, 2])))
    yaw = math.atan2(R[0, 2], R[2, 2])
    roll = math.atan2(R[1, 0], R[1, 1])
    return tuple(math.degrees(v) for v in (roll, pitch, yaw))


class RelativePoseTracker:
    """own_frame: T0^-1 T, velocities in the initial controller frame.
    world_axes: p - p0 and R R0^T, velocities left in standing axes.
    """
    def __init__(self, mode='own_frame', settle_seconds=3.0, start=None):
        if mode not in ('own_frame', 'world_axes'):
            raise ValueError(f'unknown relative pose mode: {mode}')
        self.mode = mode
        self.ready_at = (time.monotonic() if start is None else start) + settle_seconds
        self.references = {}  # kept across tracking loss so a returning controller keeps its origin

    def remaining(self, now):
        return max(0.0, self.ready_at - now)

    def reset(self, now=None):
        """Forget all references; the next tracked poses become the new origins."""
        self.references.clear()
        self.ready_at = min(self.ready_at, time.monotonic() if now is None else now)

    def apply(self, poses, now=None):
        """Return relative poses; empty until the settle delay has elapsed."""
        now = time.monotonic() if now is None else now
        if now < self.ready_at:
            return {}
        result = {}
        for name, pose in poses.items():
            T0 = self.references.setdefault(name, pose.T.copy())
            R0 = T0[:3, :3]
            T = np.eye(4)
            velocity, angular = pose.velocity, pose.angular_velocity
            if self.mode == 'own_frame':
                T[:3, :3] = R0.T @ pose.T[:3, :3]
                T[:3, 3] = R0.T @ (pose.T[:3, 3] - T0[:3, 3])
                velocity = None if velocity is None else R0.T @ velocity
                angular = None if angular is None else R0.T @ angular
            else:
                T[:3, :3] = pose.T[:3, :3] @ R0.T
                T[:3, 3] = pose.T[:3, 3] - T0[:3, 3]
            result[name] = dataclasses.replace(pose, T=T, velocity=velocity, angular_velocity=angular)
        return result
