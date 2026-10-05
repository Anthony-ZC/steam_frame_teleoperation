"""Clock sync maths and loopback exchange, absolute latency in the measurement tools."""
import subprocess
import sys
import time
import unittest
import numpy as np
from general.clock_sync import ClockSync, Responder, exchange_offset, fit_offset


class ClockMathTests(unittest.TestCase):
    def test_exchange_offset(self):
        # Remote clock 5 ms ahead, 1 ms each way.
        offset, rtt = exchange_offset(t1=0, t2=6e6, t3=6.5e6, t4=2.5e6)
        self.assertEqual((offset, rtt), (5e6, 2e6))
        # Asymmetric path (1 ms out, 3 ms back): error 1 ms, within rtt / 2.
        offset, rtt = exchange_offset(t1=0, t2=6e6, t3=6e6, t4=4e6)
        self.assertEqual(rtt, 4e6)
        self.assertLessEqual(abs(offset - 5e6), rtt / 2)

    def test_fit_offset_follows_drift(self):
        drift = 20e-6  # 20 ppm
        points = [(t, 1e6 + drift * t) for t in np.arange(0, 30e9, 2e9)]
        offset_at = fit_offset(points)
        self.assertAlmostEqual(offset_at(40e9), 1e6 + drift * 40e9, delta=1)
        self.assertEqual(fit_offset([(5, 7.0)])(100), 7.0)


class LoopbackSyncTests(unittest.TestCase):
    def test_responder_and_client(self):
        responder = Responder(9021, allowed_ip='127.0.0.1')
        sync = ClockSync('127.0.0.1', 9021)
        try:
            local_ns, offset, rtt = sync.burst(n=20, spacing=0.001)
            self.assertLess(abs(offset), 0.5e6)  # same machine and clock: offset is zero
            self.assertLess(rtt, 20e6)
            self.assertEqual(sync.quality()['bursts'], 1)
            self.assertGreater(responder.replies, 0)
        finally:
            sync.close()
            responder.close()

    def test_responder_ignores_other_addresses(self):
        responder = Responder(9024, allowed_ip='10.0.0.1')
        sync = ClockSync('127.0.0.1', 9024, timeout=0.02)
        try:
            self.assertIsNone(sync.burst(n=3, spacing=0.001))
            self.assertIsNone(sync.offset_fn())
        finally:
            sync.close()
            responder.close()

    def test_sender_sync_flag(self):
        process = subprocess.Popen([sys.executable, '-B', '-m', 'non_pc_streaming.frame_sender', '--demo',
                                    '--sync', '--sync-port', '9022', '--pc', '127.0.0.1', '--port', '9023',
                                    '--seconds', '3'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        sync = ClockSync('127.0.0.1', 9022)
        try:
            estimate = None
            deadline = time.monotonic() + 2.5
            while estimate is None and time.monotonic() < deadline:
                estimate = sync.burst(n=5, spacing=0.005)
            self.assertIsNotNone(estimate, 'sender with --sync did not answer')
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn('Clock sync: answering 127.0.0.1', stdout)
        finally:
            sync.close()
            if process.poll() is None:
                process.kill()
                process.wait()


class AbsoluteLatencyTests(unittest.TestCase):
    def test_udp_rate_with_offset(self):
        from diagnostics.measure_udp_rate import analyze
        offset = 7e9  # Frame clock 7 s ahead of the PC
        packets = []
        for i in range(200):  # 200 Hz, 2 ms transit, a new tracking sample every 2nd packet
            read_frame = offset + i * 5e6
            matrix = (0.0,) * 3 + (i * 0.001,) + (0.0,) * 8
            packets.append((i * 5e6 + 2e6, i, read_frame, frozenset({'velocity'}),
                            {'left': (matrix, (float(i // 2), 0.0, 0.0))}))
        r = analyze(packets, offset_fn=lambda _: offset)
        self.assertEqual(r['latency_source'], 'clock sync')
        self.assertAlmostEqual(r['latency_ms']['median'], 2.0)
        c = r['controllers']['left']
        self.assertAlmostEqual(c['new_sample_latency_ms']['median'], 2.0)
        self.assertAlmostEqual(c['new_sample_bound_ms']['median'], 5.0)
        self.assertIsNone(analyze(packets)['latency_ms'])  # no sync, no absolute latency

    def test_streaming_absolute_latency(self):
        from diagnostics.measure_latency import analyze
        rng = np.random.default_rng(1)
        knots = np.cumsum(rng.normal(0, 0.15, (40, 3)), axis=0)
        path = lambda t: np.column_stack([np.interp(t, np.arange(40) * 0.25, knots[:, k]) for k in range(3)])
        streaming_t = np.arange(0.5, 9.0, 0.001)
        read_t = np.arange(0.5, 9.0, 1 / 200)
        # Streaming shows the motion 15 ms late; standalone packets arrive 2 ms after the Frame read.
        traces = {'streaming': {'right': [(t, *p) for t, p in zip(streaming_t, path(streaming_t - 0.015))]},
                  'standalone': {'right': [(t + 0.002, *p) for t, p in zip(read_t, path(read_t))]},
                  'standalone_read': {'right': [(t, *p) for t, p in zip(read_t, path(read_t))]}}
        r = analyze(traces)['right']
        self.assertAlmostEqual(r['streaming_latency_ms'], 15.0, delta=1.5)
        self.assertAlmostEqual(r['standalone_latency_ms']['median'], 2.0, places=6)
        self.assertAlmostEqual(r['standalone_minus_streaming_ms'], -13.0, delta=1.5)


if __name__ == '__main__':
    unittest.main()
