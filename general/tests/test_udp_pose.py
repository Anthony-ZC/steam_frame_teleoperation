"""Real loopback transport tests, including sender process and loss handling."""
import socket
import subprocess
import sys
import time
import unittest
import numpy as np
from general.config import FIELD_GROUPS
from general.controller_state import ButtonState, ControllerState
from general.demo import demo_states
from general.pose_wire import ENTRY, HEADER, HEADER2, decode, encode, encode_states
from non_pc_streaming.udp_pose import UDPReader

MATRIX = [1, 0, 0, 0.25, 0, 1, 0, 1.2, 0, 0, 1, -0.4]


class UDPTests(unittest.TestCase):
    def setUp(self):
        self.reader = UDPReader('127.0.0.1', 9000, timeout=0.06, sender_ip='127.0.0.1')
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def tearDown(self):
        self.reader.close()
        self.sock.close()

    def send(self, session=1, sequence=1, entries=None):
        packet = encode(session, sequence, 123456789, entries if entries is not None else [(1, 1, 200, MATRIX)])
        self.sock.sendto(packet, ('127.0.0.1', 9000))
        # UDP arrives asynchronously; wait for acceptance or a short deadline.
        before = self.reader.accepted_packets + self.reader.rejected_packets
        deadline = time.monotonic() + 0.03
        while time.monotonic() < deadline:
            result = self.reader.read()
            if self.reader.accepted_packets + self.reader.rejected_packets > before:
                return result
            time.sleep(0.001)
        self.fail('loopback packet was not received')

    def test_transform_order_and_loss(self):
        poses = self.send()
        np.testing.assert_allclose(poses['left'].T[:3, 3], [0.25, 1.2, -0.4])
        np.testing.assert_array_equal(poses['left'].T[3], [0, 0, 0, 1])
        self.assertEqual(self.reader.sender_monotonic_ns, 123456789)
        self.assertEqual(self.send(sequence=2, entries=[]), {})
        self.send(sequence=3)
        time.sleep(0.08)
        self.assertEqual(self.reader.read(), {})

    def test_reorder_and_restart(self):
        self.send(sequence=10)
        self.send(sequence=9)
        self.assertEqual(self.reader.sequence, 10)
        self.send(session=2, sequence=0)
        self.assertEqual(self.reader.session, 1)
        time.sleep(0.08)
        self.send(session=2, sequence=0)
        self.assertEqual(self.reader.session, 2)

    def test_malformed_and_nonfinite(self):
        self.send()
        for packet in (b'bad', encode(1, 2, 0, []) + b'garbage', HEADER.pack(b'FVR1', 1, 1, 9, 1, 2, 0)):
            with self.assertRaises(ValueError):
                decode(packet)
        with self.assertRaises(ValueError):
            encode(1, 2, 0, [(1, 1, 200, [float('nan')] + MATRIX[1:])])
        with self.assertRaises(ValueError):
            encode(1, 2, 0, [(1, 1, 200, MATRIX), (2, 1, 200, MATRIX)])
        self.sock.sendto(b'invalid', ('127.0.0.1', 9000))
        time.sleep(0.005)
        self.assertIn('left', self.reader.read())
        self.assertGreater(self.reader.rejected_packets, 0)

    def test_real_sender_process(self):
        process = subprocess.Popen([sys.executable, '-B', '-m', 'non_pc_streaming.frame_sender',
                                    '--demo', '--pc', '127.0.0.1', '--hz', '90', '--seconds', '0.5'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        positions = []
        deadline = time.monotonic() + 3
        try:
            while process.poll() is None and time.monotonic() < deadline:
                poses = self.reader.read()
                if 'right' in poses:
                    positions.append(poses['right'].T[0, 3])
                    last = poses['right']
                time.sleep(0.002)
            stdout, stderr = process.communicate(timeout=2)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('DEMO', stdout)
            self.assertGreaterEqual(self.reader.accepted_packets, 30)
            self.assertGreater(max(positions) - min(positions), 0.005)
            self.assertEqual(self.reader.groups, frozenset(FIELD_GROUPS))  # repository config: all on
            self.assertEqual(len(last.state.finger_curl), 5)
            self.assertIn('trigger', last.state.buttons)
            time.sleep(0.01)
            self.assertEqual(self.reader.read(), {})  # sender's final empty snapshot
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


class FVR2Tests(unittest.TestCase):
    def test_round_trip_all_groups(self):
        states = list(demo_states(1.3, FIELD_GROUPS).values())
        session, sequence, sender_ns, groups, decoded = decode(encode_states(5, 6, 7, states, FIELD_GROUPS))
        self.assertEqual((session, sequence, sender_ns, groups), (5, 6, 7, frozenset(FIELD_GROUPS)))
        for original, got in zip(states, decoded):
            self.assertEqual(got.name, original.name)
            self.assertEqual(got.input_source, 'demo')
            self.assertEqual(got.buttons, original.buttons)
            self.assertEqual(got.charging, original.charging)
            self.assertEqual(got.skeletal_level, original.skeletal_level)
            for key in ('matrix', 'velocity', 'angular_velocity', 'thumbstick', 'finger_curl', 'finger_splay'):
                np.testing.assert_allclose(getattr(got, key), getattr(original, key), rtol=1e-6, atol=1e-6)
            for key in ('battery', 'trigger', 'grip'):
                self.assertAlmostEqual(getattr(got, key), getattr(original, key), places=6)

    def test_subset_and_missing_values(self):
        state = ControllerState('right', 3, MATRIX, 200, buttons={'a': ButtonState(True, True)},
                                trigger=0.0, input_source='actions')  # no grip, stick, fingers
        payload = encode_states(1, 1, 0, [state], ('analog', 'buttons', 'fingers'))
        self.assertEqual(len(payload), HEADER2.size + ENTRY.size + 6 + 16 + 37)
        _, _, _, groups, [got] = decode(payload)
        self.assertEqual(groups, frozenset({'buttons', 'analog', 'fingers'}))
        self.assertEqual(got.buttons, {'a': ButtonState(True, True)})  # unknown buttons stay absent
        self.assertEqual((got.trigger, got.grip, got.thumbstick), (0.0, None, None))
        self.assertIsNone(got.finger_curl)
        self.assertIsNone(got.skeletal_level)
        self.assertIsNone(got.velocity)  # group not sent
        _, _, _, groups, [bare] = decode(encode_states(1, 2, 0, [state]))
        self.assertEqual(groups, frozenset())
        self.assertIsNone(bare.buttons)

    def test_fvr1_still_decodes(self):
        _, _, _, groups, [state] = decode(encode(1, 1, 0, [(4, 2, 200, MATRIX)]))
        self.assertEqual((state.name, state.device_id, groups), ('right', 4, frozenset()))

    def test_malformed(self):
        state = ControllerState('left', 1, MATRIX, 200, velocity=(1.0, 0.0, 0.0), angular_velocity=(0.0, 0.0, 0.0))
        good = encode_states(1, 1, 0, [state], ('velocity',))
        for bad in (good[:-1], good + b'x', good[:7] + bytes([good[7] | 0x80]) + good[8:]):
            with self.assertRaises(ValueError):
                decode(bad)
        for velocity in ((float('inf'), 0.0, 0.0), (float('nan'), 0.0, 0.0)):  # inf, partial NaN
            state.velocity = velocity
            with self.assertRaises(ValueError):
                encode_states(1, 1, 0, [state], ('velocity',))


if __name__ == '__main__':
    unittest.main()
