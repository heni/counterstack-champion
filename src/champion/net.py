from __future__ import annotations

import logging
import queue
import socket
import threading
from typing import Optional

from . import protocol
from .protocol import Envelope, ProtocolError

log = logging.getLogger(__name__)

_RECV_CHUNK = 4096
_EOF = object()


class Connection:
    """TCP/JSONL channel to the CounterStack server.

    Real-time path: each recv() call typically returns one full envelope ending
    in '\\n' — we parse it directly. Split / coalesced reads fall through a
    minimal-remainder branch and bump fallback_count, which is reported in the
    SLO summary at match end.
    """

    def __init__(self, host: str, port: int, *, connect_timeout: float = 10.0):
        self.host = host
        self.port = port
        self.fallback_count = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(connect_timeout)
        self._sock.connect((host, port))
        self._sock.settimeout(None)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._inbox: queue.Queue = queue.Queue()
        self._outbox: queue.Queue = queue.Queue()
        self._closed = threading.Event()
        self._recv_thread = threading.Thread(
            target=self._recv_loop, name="cs-recv", daemon=True
        )
        self._send_thread = threading.Thread(
            target=self._send_loop, name="cs-send", daemon=True
        )
        self._recv_thread.start()
        self._send_thread.start()

    def send(self, env: Envelope) -> None:
        if self._closed.is_set():
            log.warning("send after close, dropping %s envelope", env.t)
            return
        self._outbox.put(env)

    def recv(self, timeout: Optional[float] = None) -> Optional[Envelope]:
        item = self._inbox.get(timeout=timeout)
        if item is _EOF:
            return None
        return item

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
        self._outbox.put(_EOF)

    def _recv_loop(self) -> None:
        remainder = b""
        try:
            while not self._closed.is_set():
                try:
                    data = self._sock.recv(_RECV_CHUNK)
                except OSError:
                    break
                if not data:
                    break
                # Fast path: empty remainder, single full envelope.
                if (
                    not remainder
                    and data.endswith(b"\n")
                    and data.count(b"\n") == 1
                ):
                    self._dispatch(data[:-1])
                    continue
                # Slow path: bump metric, split-and-buffer.
                self.fallback_count += 1
                buf = remainder + data
                *lines, remainder = buf.split(b"\n")
                for line in lines:
                    if line:
                        self._dispatch(line)
        finally:
            self._inbox.put(_EOF)

    def _send_loop(self) -> None:
        while True:
            item = self._outbox.get()
            if item is _EOF:
                break
            data = protocol.encode(item)
            try:
                self._sock.sendall(data)
            except OSError as e:
                log.warning("send failed: %s", e)
                break

    def _dispatch(self, line: bytes) -> None:
        try:
            env = protocol.decode(line)
        except ProtocolError as e:
            log.warning("decode failed: %s", e)
            return
        self._inbox.put(env)
