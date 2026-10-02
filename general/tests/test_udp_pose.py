"""Real loopback transport tests, including sender process and loss handling."""
import socket
import subprocess
import sys
import time
import unittest
import numpy as np
from general.pose_wire import HEADER, decode, encode
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
                time.sleep(0.002)
            stdout, stderr = process.communicate(timeout=2)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('DEMO', stdout)
            self.assertGreaterEqual(self.reader.accepted_packets, 30)
            self.assertGreater(max(positions) - min(positions), 0.005)
            time.sleep(0.01)
            self.assertEqual(self.reader.read(), {})  # sender's final empty snapshot
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


if __name__ == '__main__':
    unittest.main()
