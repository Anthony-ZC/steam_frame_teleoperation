"""Optional NTP-style clock synchronization between the Frame sender and PC tools.

Stdlib only, so it runs on Frame. The sender starts a Responder only with
--sync; the PC measurement tools use ClockSync to learn the offset between the
two perf_counter clocks, which turns packet timestamps into absolute latency.

  PC sends t1 -> Frame receives t2, replies at t3 -> PC receives t4
  offset = ((t2 - t1) + (t3 - t4)) / 2   (remote clock minus local clock)
  rtt    = (t4 - t1) - (t3 - t2)

The error is bounded by path asymmetry, at most rtt / 2; the fastest exchanges
are kept because they saw the least queueing.
"""
import socket
import struct
import threading
import time

REQUEST = struct.Struct('!4sQ')
REPLY = struct.Struct('!4sQQQ')
DEFAULT_PORT = 9001


def exchange_offset(t1, t2, t3, t4):
    """Return (offset_ns, rtt_ns) of one exchange; offset = remote - local."""
    return ((t2 - t1) + (t3 - t4)) / 2, (t4 - t1) - (t3 - t2)


def fit_offset(points):
    """Least-squares line through [(local_ns, offset_ns)]: returns offset_at(local_ns)."""
    if not points:
        raise ValueError('no clock sync estimates')
    t0 = points[0][0]
    xs = [t - t0 for t, _ in points]
    ys = [o for _, o in points]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    var = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var if var else 0.0
    return lambda local_ns: mean_y + slope * (local_ns - t0 - mean_x)


class Responder:
    """Answers sync requests from one PC address; a daemon thread, idle until asked."""
    def __init__(self, port=DEFAULT_PORT, allowed_ip=None, bind='0.0.0.0'):
        self.allowed_ip = allowed_ip
        self.replies = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((bind, port))
        self.sock.settimeout(0.5)
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                data, source = self.sock.recvfrom(64)
            except socket.timeout:
                continue
            except OSError:
                break
            t2 = time.perf_counter_ns()
            if (self.allowed_ip and source[0] != self.allowed_ip) or len(data) != REQUEST.size:
                continue
            magic, t1 = REQUEST.unpack(data)
            if magic != b'FVRS':
                continue
            try:
                self.sock.sendto(REPLY.pack(b'FVRR', t1, t2, time.perf_counter_ns()), source)
                self.replies += 1
            except OSError:
                pass

    def close(self):
        self._stop.set()
        self.sock.close()


class ClockSync:
    """PC side: repeated bursts of exchanges, drift-corrected offset estimate."""
    def __init__(self, remote_ip, port=DEFAULT_PORT, timeout=0.05):
        self.remote = (remote_ip, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self.estimates = []  # (local_ns, offset_ns, rtt_ns) per burst
        self.rtts = []       # every exchange, ns
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def burst(self, n=40, spacing=0.002):
        """Run n exchanges; store and return (local_ns, offset_ns, rtt_ns) or None."""
        exchanges = []
        for _ in range(n):
            t1 = time.perf_counter_ns()
            try:
                self.sock.sendto(REQUEST.pack(b'FVRS', t1), self.remote)
                while True:  # skip stale replies from earlier timeouts
                    data, _ = self.sock.recvfrom(64)
                    t4 = time.perf_counter_ns()
                    if len(data) == REPLY.size:
                        magic, r1, t2, t3 = REPLY.unpack(data)
                        if magic == b'FVRR' and r1 == t1:
                            offset, rtt = exchange_offset(t1, t2, t3, t4)
                            exchanges.append(((t1 + t4) / 2, offset, rtt))
                            break
            except (socket.timeout, OSError):
                pass
            time.sleep(spacing)
        if not exchanges:
            return None
        exchanges.sort(key=lambda e: e[2])
        best = exchanges[:max(1, len(exchanges) // 4)]
        best.sort(key=lambda e: e[1])
        local_ns, offset, _ = best[len(best) // 2]
        estimate = (local_ns, offset, exchanges[0][2])
        with self._lock:
            self.estimates.append(estimate)
            self.rtts.extend(e[2] for e in exchanges)
        return estimate

    def start(self, interval=2.0):
        """Burst now and then every `interval` seconds in a background thread."""
        def loop():
            while not self._stop.is_set():
                self.burst()
                self._stop.wait(interval)
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def offset_fn(self):
        """offset_at(local_ns) from all bursts so far, or None if nothing answered."""
        with self._lock:
            points = [(t, o) for t, o, _ in self.estimates]
        return fit_offset(points) if points else None

    def quality(self):
        with self._lock:
            estimates, rtts = list(self.estimates), sorted(self.rtts)
        if not estimates:
            return None
        fit = fit_offset([(t, o) for t, o, _ in estimates])
        span = estimates[-1][0] - estimates[0][0]
        drift = (fit(estimates[-1][0]) - fit(estimates[0][0])) / span if span else 0.0
        return {'bursts': len(estimates), 'exchanges': len(rtts), 'offset_ms': fit(estimates[-1][0]) / 1e6,
                'rtt_min_ms': rtts[0] / 1e6, 'rtt_median_ms': rtts[len(rtts) // 2] / 1e6,
                'error_bound_ms': min(e[2] for e in estimates) / 2e6, 'drift_ppm': drift * 1e6}

    def close(self):
        self.stop()
        self.sock.close()
