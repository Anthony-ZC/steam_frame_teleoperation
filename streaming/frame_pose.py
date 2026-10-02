"""SteamVR device poses; no rendering, action manifest, or Steam app ID needed."""
import time
import numpy as np
from general.poses import Pose


class PoseReader:
    def __init__(self):
        import openvr
        self.vr = openvr
        self.system = openvr.init(openvr.VRApplication_Background)
        self.buffer = (openvr.TrackedDevicePose_t * openvr.k_unMaxTrackedDeviceCount)()

    def read(self):
        vr = self.vr
        self.system.getDeviceToAbsoluteTrackingPose(
            vr.TrackingUniverseStanding, 0.0, self.buffer)
        received = time.monotonic()
        result = {}
        for i, pose in enumerate(self.buffer):
            if self.system.getTrackedDeviceClass(i) != vr.TrackedDeviceClass_Controller:
                continue
            if not pose.bDeviceIsConnected or not pose.bPoseIsValid:
                continue
            # Reject inferred/degraded tracking for this robotics-oriented example.
            if pose.eTrackingResult != vr.TrackingResult_Running_OK:
                continue
            role = self.system.getControllerRoleForTrackedDeviceIndex(i)
            name = {vr.TrackedControllerRole_LeftHand: 'left',
                    vr.TrackedControllerRole_RightHand: 'right'}.get(role, f'device_{i}')
            T = np.eye(4)
            T[:3, :] = np.array([[pose.mDeviceToAbsoluteTracking.m[r][c]
                                 for c in range(4)] for r in range(3)])
            result[name] = Pose(name, i, T, received, int(pose.eTrackingResult))
        return result

    def close(self):
        self.vr.shutdown()
