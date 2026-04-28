import socket
import threading
import time
from contextlib import contextmanager

import pytest

from champion import protocol
from champion.net import Connection
from champion.protocol import Envelope


@contextmanager
def _listener():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted: dict[str, socket.socket | None] = {"sock": None}

    def _accept() -> None:
        accepted["sock"], _ = srv.accept()

    t = threading.Thread(target=_accept, daemon=True)
    t.start()
    try:
        yield port, accepted
    finally:
        if accepted["sock"] is not None:
            accepted["sock"].close()
        srv.close()


def _wait_for_accept(accepted: dict[str, socket.socket | None]) -> socket.socket:
    deadline = time.monotonic() + 2.0
    while accepted["sock"] is None and time.monotonic() < deadline:
        time.sleep(0.001)
    assert accepted["sock"] is not None, "listener did not accept in time"
    return accepted["sock"]


def test_send_to_server():
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        peer = _wait_for_accept(accepted)
        try:
            conn.send(protocol.hello("alice", "tok"))
            peer.settimeout(2.0)
            data = peer.recv(4096)
            assert data.endswith(b"\n")
            decoded = protocol.decode(data[:-1])
            assert decoded.t == "hello"
            assert decoded.p["agent_name"] == "alice"
        finally:
            conn.close()


def test_recv_single_envelope_fast_path():
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        peer = _wait_for_accept(accepted)
        try:
            peer.sendall(protocol.encode(Envelope(t="welcome", p={"match_id": "m-7"})))
            env = conn.recv(timeout=2.0)
            assert env is not None
            assert env.t == "welcome"
            assert env.p["match_id"] == "m-7"
            assert conn.fallback_count == 0
        finally:
            conn.close()


def test_recv_coalesced_envelopes_uses_fallback():
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        peer = _wait_for_accept(accepted)
        try:
            blob = (
                protocol.encode(Envelope(t="welcome", p={"match_id": "m-1"}))
                + protocol.encode(Envelope(t="match_start", p={"seed": 42}))
            )
            peer.sendall(blob)
            env1 = conn.recv(timeout=2.0)
            env2 = conn.recv(timeout=2.0)
            assert env1.t == "welcome"
            assert env2.t == "match_start"
            assert conn.fallback_count == 1
        finally:
            conn.close()


def test_recv_split_envelope_uses_fallback():
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        peer = _wait_for_accept(accepted)
        try:
            full = protocol.encode(Envelope(t="welcome", p={"match_id": "m-1"}))
            half = len(full) // 2
            peer.sendall(full[:half])
            time.sleep(0.05)
            peer.sendall(full[half:])
            env = conn.recv(timeout=2.0)
            assert env.t == "welcome"
            assert conn.fallback_count >= 1
        finally:
            conn.close()


def test_recv_returns_none_on_eof():
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        peer = _wait_for_accept(accepted)
        try:
            peer.shutdown(socket.SHUT_RDWR)
            peer.close()
            accepted["sock"] = None
            env = conn.recv(timeout=2.0)
            assert env is None
        finally:
            conn.close()


def test_malformed_line_is_dropped_warning_only():
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        peer = _wait_for_accept(accepted)
        try:
            peer.sendall(b"not a json line\n")
            peer.sendall(protocol.encode(Envelope(t="welcome", p={})))
            env = conn.recv(timeout=2.0)
            assert env.t == "welcome"
        finally:
            conn.close()


def test_connect_timeout_on_unreachable():
    with pytest.raises((OSError, ConnectionRefusedError)):
        Connection("127.0.0.1", 1, connect_timeout=0.5)


def test_send_after_close_drops_with_warning(caplog):
    with _listener() as (port, accepted):
        conn = Connection("127.0.0.1", port)
        _wait_for_accept(accepted)
        conn.close()
        with caplog.at_level("WARNING", logger="champion.net"):
            conn.send(protocol.hello("a", "b"))
        assert any(
            "send after close" in record.message for record in caplog.records
        ), [r.message for r in caplog.records]
