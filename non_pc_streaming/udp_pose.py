"""Nonblocking UDP snapshot reader implementing general.readers.ControllerReader."""
import ipaddress
import socket
import time
import numpy as np
from general.poses import Pose
from general.pose_wire import MAX_PACKET, decode
from general.readers import ControllerReader


class UDPReader(ControllerReader):
    def __init__(self, bind='0.0.0.0', port=9000, timeout=0.25, sender_ip=None):
        if not 1 <= port <= 65535 or not np.isfinite(timeout) or timeout <= 0:
            raise ValueError('port and timeout must be valid and positive')
        self.sender_ip = str(ipaddress.IPv4Address(sender_ip)) if sender_ip else None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.bind((bind, port))
            self.socket.setblocking(False)
        except BaseException:
            self.socket.close()
            raise
        self.timeout = timeout
        self.session = self.sequence = self.source_ip = None
        self.last_received = 0.0
        self.sender_monotonic_ns = None
        self.poses = {}
        self.accepted_packets = self.rejected_packets = 0

    def read(self):
        # Bounded drain: keep the latest available snapshot, without waiting.
        for _ in range(256):
            try:
                payload, source = self.socket.recvfrom(MAX_PACKET + 1)
            except BlockingIOError:
                break
            received = time.monotonic()
            if self.sender_ip and source[0] != self.sender_ip:
                self.rejected_packets += 1
                continue
            try:
                session, sequence, sender_ns, entries = decode(payload)
            except (ValueError, OverflowError):
                self.rejected_packets += 1
                continue
            active = received - self.last_received <= self.timeout
            if active and (source[0] != self.source_ip or session != self.session):
                self.rejected_packets += 1
                continue
            if (source[0] == self.source_ip and session == self.session
                    and self.sequence is not None and sequence <= self.sequence):
                self.rejected_packets += 1
                continue
            poses = {}
            for device, role, tracking, matrix in entries:
                name = {1: 'left', 2: 'right'}.get(role, f'device_{device}')
                transform = np.eye(4)
                transform[:3, :] = np.array(matrix).reshape(3, 4)
                poses[name] = Pose(name, device, transform, received, tracking)
            self.poses = poses  # empty snapshot immediately clears lost tracking
            self.session, self.sequence = session, sequence
            self.source_ip = source[0]
            self.sender_monotonic_ns = sender_ns
            self.last_received = received
            self.accepted_packets += 1
        if time.monotonic() - self.last_received > self.timeout:
            return {}
        return dict(self.poses)

    def close(self):
        self.socket.close()
