from __future__ import annotations

import socket
import threading
import time
from typing import Optional

from champion import protocol
from champion.protocol import Envelope


class MockServer:
    """Scriptable localhost JSONL listener used by agent tests.

    Pattern: instantiate, run agent in a thread, then drive the wire from the
    test thread with explicit recv/send calls.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._client: Optional[socket.socket] = None
        self._buf = b""
        self._accept_thread = threading.Thread(
            target=self._accept, name="mock-accept", daemon=True
        )
        self._accept_thread.start()

    def _accept(self) -> None:
        try:
            sock, _ = self._sock.accept()
            self._client = sock
        except OSError:
            pass

    def wait_for_connect(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while self._client is None and time.monotonic() < deadline:
            time.sleep(0.001)
        if self._client is None:
            raise TimeoutError(f"client did not connect within {timeout}s")

    def send(self, env: Envelope) -> None:
        assert self._client is not None
        self._client.sendall(protocol.encode(env))

    def send_raw(self, data: bytes) -> None:
        assert self._client is not None
        self._client.sendall(data)

    def recv(self, timeout: float = 2.0) -> Envelope:
        assert self._client is not None
        deadline = time.monotonic() + timeout
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"no envelope within {timeout}s; buf={self._buf!r}"
                )
            self._client.settimeout(max(0.01, remaining))
            try:
                chunk = self._client.recv(4096)
            except socket.timeout as e:
                raise TimeoutError(f"recv timed out; buf={self._buf!r}") from e
            if not chunk:
                raise EOFError(f"client closed; buf={self._buf!r}")
            self._buf += chunk
        idx = self._buf.index(b"\n")
        line, self._buf = self._buf[:idx], self._buf[idx + 1 :]
        return protocol.decode(line)

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._client.close()
            except OSError:
                pass
            self._client = None
        try:
            self._sock.close()
        except OSError:
            pass


def empty_tick(tick_no: int = 1, *, keepalive_nonce: int | None = None) -> Envelope:
    """A minimal but spec-shaped tick payload, optionally carrying a keepalive ping."""
    keepalive = {"ping": {"nonce": keepalive_nonce}} if keepalive_nonce is not None else None
    return Envelope(
        t="tick",
        p={
            "tick": tick_no,
            "duration_ns": 2_000_000,
            "own": {
                "op": None,
                "accepted": None,
                "active_piece": None,
                "locked": False,
                "cleared_rows": 0,
                "score": 0,
                "frozen": False,
            },
            "opp": None,
            "info": None,
            "keepalive": keepalive,
            "rejected": {"own": 0, "opp": 0, "info": 0, "keepalive": 0},
            "own_board_delta": [],
            "opp_board_delta": [],
            "my_queue": ["I", "L", "P"],
            "opp_queue": None,
        },
    )
