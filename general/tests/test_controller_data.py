"""Relative pose, config, legacy decoding, the shared OpenVR sampler (with a fake runtime), and viewer smoke tests."""
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from general import config as config_file
from general.config import Config, FIELD_GROUPS
from general.openvr_sampler import OpenVRSampler, decode_legacy
from general.poses import Pose
from general.readers import DemoReader
from general.relative_pose import RelativePoseTracker, euler_yxz_deg


def rot_y(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def pose(name, R, p, v=None, w=None):
    T = np.eye(4)
    T[:3, :3], T[:3, 3] = R, p
    return Pose(name, 0, T, 0.0, 200, None if v is None else np.array(v, float),
                None if w is None else np.array(w, float))


class RelativePoseTests(unittest.TestCase):
    def test_settle_then_identity_at_capture(self):
        tracker = RelativePoseTracker('own_frame', settle_seconds=2, start=10)
        poses = {'left': pose('left', rot_y(0.5), [1, 2, 3])}
        self.assertEqual(tracker.apply(poses, now=11), {})
        self.assertAlmostEqual(tracker.remaining(11), 1)
        rel = tracker.apply(poses, now=12)['left']
        np.testing.assert_allclose(rel.T, np.eye(4), atol=1e-12)

    def test_own_frame_motion_and_velocity(self):
        tracker = RelativePoseTracker('own_frame', 0, start=0)
        tracker.apply({'right': pose('right', rot_y(math.pi/2), [0, 0, 0])}, now=0)
        # Moving +X in the standing frame is -Z... after the initial 90 deg yaw.
        rel = tracker.apply({'right': pose('right', rot_y(math.pi/2), [1, 0, 0], v=[1, 0, 0], w=[0, 2, 0])}, now=1)['right']
        np.testing.assert_allclose(rel.T[:3, 3], rot_y(math.pi/2).T @ [1, 0, 0], atol=1e-12)
        np.testing.assert_allclose(rel.T[:3, 3], [0, 0, 1], atol=1e-12)
        np.testing.assert_allclose(rel.velocity, [0, 0, 1], atol=1e-12)
        np.testing.assert_allclose(rel.angular_velocity, [0, 2, 0], atol=1e-12)
        np.testing.assert_allclose(rel.T[:3, :3], np.eye(3), atol=1e-12)

    def test_world_axes(self):
        tracker = RelativePoseTracker('world_axes', 0, start=0)
        tracker.apply({'left': pose('left', rot_y(0.3), [1, 1, 1])}, now=0)
        rel = tracker.apply({'left': pose('left', rot_y(0.8), [1.5, 1, 1], v=[1, 0, 0], w=[0, 1, 0])}, now=1)['left']
        np.testing.assert_allclose(rel.T[:3, 3], [0.5, 0, 0], atol=1e-12)
        np.testing.assert_allclose(rel.T[:3, :3], rot_y(0.5), atol=1e-12)
        np.testing.assert_allclose(rel.velocity, [1, 0, 0])

    def test_late_controller_and_reset(self):
        tracker = RelativePoseTracker('world_axes', 0, start=0)
        tracker.apply({'left': pose('left', np.eye(3), [0, 0, 0])}, now=0)
        rel = tracker.apply({'left': pose('left', np.eye(3), [1, 0, 0]),
                             'right': pose('right', np.eye(3), [5, 0, 0])}, now=1)
        np.testing.assert_allclose(rel['left'].T[:3, 3], [1, 0, 0])
        np.testing.assert_allclose(rel['right'].T[:3, 3], [0, 0, 0])  # captured on first sight
        # A temporarily lost controller keeps its reference.
        tracker.apply({}, now=2)
        rel = tracker.apply({'left': pose('left', np.eye(3), [2, 0, 0])}, now=3)
        np.testing.assert_allclose(rel['left'].T[:3, 3], [2, 0, 0])
        tracker.reset(now=4)
        rel = tracker.apply({'left': pose('left', np.eye(3), [2, 0, 0])}, now=4)
        np.testing.assert_allclose(rel['left'].T[:3, 3], [0, 0, 0])

    def test_reset_during_settle_captures_immediately(self):
        tracker = RelativePoseTracker('own_frame', 5, start=0)
        tracker.reset(now=1)
        self.assertIn('left', tracker.apply({'left': pose('left', np.eye(3), [0, 0, 0])}, now=1))

    def test_euler(self):
        def Rx(a):
            c, s = math.cos(a), math.sin(a)
            return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])

        def Rz(a):
            c, s = math.cos(a), math.sin(a)
            return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        R = rot_y(math.radians(30)) @ Rx(math.radians(-20)) @ Rz(math.radians(10))
        np.testing.assert_allclose(euler_yxz_deg(R), (10, -20, 30), atol=1e-9)


class ConfigTests(unittest.TestCase):
    def test_repository_config_and_defaults(self):
        self.assertEqual(config_file.load(), Config())
        self.assertEqual(config_file.parse({}), Config())

    def test_values_and_validation(self):
        cfg = config_file.parse({'fields': {'fingers': False, 'velocity': False},
                                 'relative_pose': {'mode': 'world_axes', 'settle_seconds': 1},
                                 'input': {'app_type': 'scene'}})
        self.assertEqual(cfg.fields, frozenset({'battery', 'buttons', 'analog'}))
        self.assertEqual((cfg.relative_mode, cfg.settle_seconds, cfg.app_type), ('world_axes', 1.0, 'scene'))
        for bad in ({'fields': {'finger': True}}, {'relative_pose': {'mode': 'local'}},
                    {'relative_pose': {'settle_seconds': -1}}, {'input': {'app_type': 'game'}},
                    {'fields': {'buttons': 1}}, {'extra': {}}):
            with self.assertRaises(ValueError, msg=bad):
                config_file.parse(bad)
        with self.assertRaises(FileNotFoundError):
            config_file.load('does_not_exist.toml')


class LegacyTests(unittest.TestCase):
    def test_default_and_knuckles_layouts(self):
        axes = [(0.1, 0.2), (0.7, 0), (0.4, 0), (0.5, -0.5), (0, 0)]
        state = decode_legacy(1 << 33, (1 << 33) | (1 << 7), axes)
        self.assertTrue(state['buttons']['trigger'].pressed)
        self.assertTrue(state['buttons']['a'].touched)
        self.assertFalse(state['buttons']['a'].pressed)
        self.assertEqual((state['trigger'], state['grip'], state['thumbstick']), (0.7, 0.4, (0.1, 0.2)))
        knuckles = decode_legacy(1 << 2, 0, axes, 'knuckles')
        self.assertTrue(knuckles['buttons']['a'].pressed)
        self.assertEqual(knuckles['thumbstick'], (0.5, -0.5))


def fake_openvr(devices, legacy=None, input_error=True, quit_event=False):
    """Minimal pyopenvr stand-in: devices = [(class, role, connected, valid, tracking, x)]."""
    vec = lambda *v: SimpleNamespace(v=list(v))
    poses = []
    for cls, role, connected, valid, tracking, x in devices:
        m = [[1, 0, 0, x], [0, 1, 0, 1.0], [0, 0, 1, -0.5]]
        poses.append(SimpleNamespace(mDeviceToAbsoluteTracking=SimpleNamespace(m=m),
                                     vVelocity=vec(x, 0, 0), vAngularVelocity=vec(0, 1, 0),
                                     eTrackingResult=tracking, bPoseIsValid=valid,
                                     bDeviceIsConnected=connected))
    events = [quit_event]

    def poll(event):
        if events and events[0]:
            events.pop()
            event.eventType = 700
            return True
        return False

    def controller_state(device):
        pressed, touched, axes = legacy or (0, 0, [(0, 0)] * 5)
        raw = SimpleNamespace(ulButtonPressed=pressed, ulButtonTouched=touched,
                              rAxis=[SimpleNamespace(x=a, y=b) for a, b in axes])
        return True, raw

    system = SimpleNamespace(
        pollNextEvent=poll, acknowledgeQuit_Exiting=lambda: None,
        getDeviceToAbsoluteTrackingPose=lambda *a: None,
        getTrackedDeviceClass=lambda d: devices[d][0],
        getControllerRoleForTrackedDeviceIndex=lambda d: devices[d][1],
        getFloatTrackedDeviceProperty=lambda d, p: 0.75,
        getBoolTrackedDeviceProperty=lambda d, p: True,
        getStringTrackedDeviceProperty=lambda d, p: 'knuckles',
        getControllerState=controller_state)

    def no_input():
        raise RuntimeError('no input')
    # `(TrackedDevicePose_t * n)()` builds the pose buffer.
    pose_type = type('PoseType', (), {'__mul__': lambda self, n: lambda: poses})()
    vr = SimpleNamespace(
        TrackedDevicePose_t=pose_type,
        k_unMaxTrackedDeviceCount=len(devices), VREvent_t=lambda: SimpleNamespace(eventType=0),
        VREvent_Quit=700, TrackingUniverseStanding=1, TrackedDeviceClass_Controller=2,
        TrackingResult_Running_OK=200, Prop_DeviceBatteryPercentage_Float=1012,
        Prop_DeviceIsCharging_Bool=1011, Prop_ControllerType_String=7000,
        VRInput=no_input if input_error else None)
    return vr, system


class SamplerTests(unittest.TestCase):
    DEVICES = [(1, 0, True, True, 200, 0.0),     # HMD: ignored
               (2, 1, True, True, 200, -0.3),    # left
               (2, 2, True, True, 200, 0.3),     # right
               (2, 2, True, True, 200, 0.9),     # second "right": device name
               (2, 1, True, True, 101, 0.0),     # degraded tracking: ignored
               (2, 0, True, False, 200, 0.0)]    # invalid pose: ignored

    def test_pose_only(self):
        vr, system = fake_openvr(self.DEVICES)
        sampler = OpenVRSampler(vr, system)
        states = sampler.sample()
        self.assertEqual(sorted(states), ['device_3', 'left', 'right'])
        self.assertIsNone(sampler.input_error)  # no input groups: IVRInput never touched
        left = states['left']
        self.assertEqual(left.matrix[3], -0.3)
        self.assertIsNone(left.velocity)
        self.assertIsNone(left.buttons)

    def test_all_fields_with_legacy_fallback(self):
        axes = [(0, 0), (0.6, 0), (0.2, 0), (0.1, -0.4), (0, 0)]
        vr, system = fake_openvr(self.DEVICES, legacy=(1 << 2, 1 << 33, axes))
        sampler = OpenVRSampler(vr, system, FIELD_GROUPS)
        self.assertIn('no input', sampler.input_error)
        right = sampler.sample()['right']
        self.assertEqual(right.velocity, (0.3, 0, 0))
        self.assertEqual((right.battery, right.charging, right.controller_type), (0.75, True, 'knuckles'))
        self.assertTrue(right.buttons['a'].pressed)  # knuckles legacy layout
        self.assertTrue(right.buttons['trigger'].touched)
        self.assertEqual((right.trigger, right.grip, right.thumbstick), (0.6, 0.2, (0.1, -0.4)))
        self.assertIsNone(right.finger_curl)  # no legacy finger data
        self.assertEqual(right.input_source, 'legacy')

    def test_no_legacy_and_quit(self):
        vr, system = fake_openvr(self.DEVICES, quit_event=True)
        sampler = OpenVRSampler(vr, system, {'buttons'}, legacy_fallback=False, max_controllers=1)
        states = sampler.sample()
        self.assertTrue(sampler.quit_requested)
        self.assertEqual(len(states), 1)
        self.assertIsNone(states['left'].buttons)
        self.assertIsNone(states['left'].input_source)


class DemoAndViewerTests(unittest.TestCase):
    def test_demo_fields(self):
        full = DemoReader().read()['left']
        self.assertEqual(len(full.state.finger_curl), 5)
        self.assertIsNotNone(full.velocity)
        bare = DemoReader(()).read()['right']
        self.assertIsNone(bare.velocity)
        self.assertIsNone(bare.state.buttons)
        self.assertIsNone(bare.state.finger_curl)

    def test_viewer_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            reduced = Path(tmp, 'reduced.toml')
            reduced.write_text('[fields]\nfingers = false\nbuttons = false\nanalog = false\n'
                               '[relative_pose]\nenabled = false\n', encoding='utf-8')
            for extra in ([], ['--config', str(reduced)]):
                out = Path(tmp, f'preview{len(extra)}.png')
                result = subprocess.run([sys.executable, '-B', '-m', 'general.visualize_poses', '--demo',
                                         '--save-preview', str(out), *extra],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertGreater(out.stat().st_size, 10000)


if __name__ == '__main__':
    unittest.main()
