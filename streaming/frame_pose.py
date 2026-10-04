"""SteamVR controller reader; no rendering or Steam app ID needed."""
import time
from general.config import Config
from general.openvr_sampler import OpenVRSampler, init_openvr
from general.poses import pose_from_state
from general.readers import ControllerReader


class SteamVRReader(ControllerReader):
    def __init__(self, config=None):
        import openvr
        config = config or Config()
        self.vr = openvr
        self.system = init_openvr(openvr, config.app_type)
        # Fully tracked controllers only: inferred/degraded tracking is rejected
        # for this robotics-oriented example.
        self.sampler = OpenVRSampler(openvr, self.system, config.fields, config.legacy_fallback)

    def read(self):
        states = self.sampler.sample()
        received = time.monotonic()
        return {name: pose_from_state(state, received) for name, state in states.items()}

    def close(self):
        self.vr.shutdown()


PoseReader = SteamVRReader
