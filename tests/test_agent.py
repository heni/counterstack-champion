from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import pytest

from champion.agent import Agent, HandshakeError
from champion.protocol import Envelope

from .mock_server import MockServer, empty_tick


@dataclass
class _AgentRun:
    agent: Agent
    thread: threading.Thread
    result: dict[str, Any] = field(default_factory=lambda: {"exit_code": None, "exc": None})


@pytest.fixture
def server():
    s = MockServer()
    yield s
    s.close()


def _spawn_agent(port: int, **kwargs: Any) -> _AgentRun:
    agent = Agent("127.0.0.1", port, **kwargs)
    run = _AgentRun(agent=agent, thread=None)  # type: ignore[arg-type]

    def _runner() -> None:
        try:
            run.result["exit_code"] = agent.run()
        except Exception as e:
            run.result["exc"] = e

    t = threading.Thread(target=_runner, name="agent-under-test", daemon=True)
    run.thread = t
    t.start()
    return run


def _drive_handshake(server: MockServer, *, configs: list[dict[str, Any]] | None = None) -> Envelope:
    """Drive hello → welcome → ready and return the ready envelope."""
    if configs is None:
        configs = [{"name": "pentris-7", "mode": "qualification"}]
    hello = server.recv()
    assert hello.t == "hello"
    server.send(
        Envelope(
            t="welcome",
            p={"match_id": "m-test", "protocol_version": 5, "available_configs": configs},
        )
    )
    return server.recv()


def test_handshake_then_match_end(server: MockServer) -> None:
    run = _spawn_agent(server.port, agent_name="alice", token="tok")
    server.wait_for_connect()
    hello = server.recv()
    assert hello.t == "hello" and hello.q is None
    assert hello.p == {
        "agent_name": "alice",
        "token": "tok",
        "protocol_version": 5,
    }
    server.send(
        Envelope(
            t="welcome",
            p={
                "match_id": "m-test",
                "protocol_version": 5,
                "available_configs": [{"name": "pentris-7", "mode": "qualification"}],
            },
        )
    )
    ready = server.recv()
    assert ready.t == "ready" and ready.q is None
    assert ready.p == {"config_name": "pentris-7"}
    server.send(
        Envelope(t="match_start", p={"seed": 42, "config": {}, "initial_state": {}})
    )
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert not run.thread.is_alive()
    assert run.result["exc"] is None
    assert run.result["exit_code"] == 0
    assert run.agent.match_id == "m-test"
    assert run.agent.config_name == "pentris-7"


def test_keepalive_pong_byte_perfect(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    server.send(empty_tick(tick_no=1, keepalive_nonce=777))
    pong = server.recv()
    assert pong.t == "pong"
    assert pong.q == "keepalive"
    assert pong.p == {"nonce": 777}
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.result["exit_code"] == 0
    assert run.agent.ping_count == 1
    assert run.agent.tick_count == 1


def test_keepalive_responds_to_each_ping(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    nonces = [10, 20, 30]
    for i, n in enumerate(nonces, start=1):
        server.send(empty_tick(tick_no=i, keepalive_nonce=n))
        pong = server.recv()
        assert pong.p == {"nonce": n}
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.agent.ping_count == len(nonces)


def test_handshake_fails_on_empty_available_configs(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    server.recv()  # hello
    server.send(
        Envelope(
            t="welcome",
            p={"match_id": "m-x", "protocol_version": 5, "available_configs": []},
        )
    )
    run.thread.join(timeout=3.0)
    assert isinstance(run.result["exc"], HandshakeError)
    assert "available_configs" in str(run.result["exc"])


def test_handshake_fails_when_configs_lack_usable_name(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    server.recv()  # hello
    server.send(
        Envelope(
            t="welcome",
            p={
                "match_id": "m-x",
                "protocol_version": 5,
                "available_configs": [{"mode": "qualification"}, {"name": ""}],
            },
        )
    )
    run.thread.join(timeout=3.0)
    assert isinstance(run.result["exc"], HandshakeError)


def test_keepalive_with_invalid_nonce_is_ignored(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    bad_tick = empty_tick(tick_no=1, keepalive_nonce=1)
    bad_tick.p["keepalive"] = {"ping": {"nonce": "not-an-int"}}
    server.send(bad_tick)
    server.send(empty_tick(tick_no=2, keepalive_nonce=999))
    pong = server.recv()
    assert pong.p == {"nonce": 999}
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.result["exit_code"] == 0
    assert run.agent.ping_count == 1
    assert run.agent.tick_count == 2


def test_handshake_fails_on_server_error_during_handshake(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    server.recv()  # hello
    server.send(
        Envelope(
            t="welcome",
            p={
                "match_id": "m-x",
                "protocol_version": 5,
                "available_configs": [{"name": "pentris-7"}],
            },
        )
    )
    server.recv()  # ready
    server.send(
        Envelope(
            t="error",
            p={"code": "config_required", "message": "missing field"},
        )
    )
    run.thread.join(timeout=3.0)
    assert isinstance(run.result["exc"], HandshakeError)
    assert "error" in str(run.result["exc"]).lower()


def test_handshake_fails_on_silent_fin(server: MockServer) -> None:
    """Repro: server FINs after our valid ready (cf. bug-report-01.md)."""
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    server.recv()  # hello
    server.send(
        Envelope(
            t="welcome",
            p={
                "match_id": "m-x",
                "protocol_version": 5,
                "available_configs": [{"name": "pentris-7"}],
            },
        )
    )
    server.recv()  # ready
    server.close()  # silent FIN, no match_start
    run.thread.join(timeout=3.0)
    assert isinstance(run.result["exc"], HandshakeError)
    assert "closed" in str(run.result["exc"]).lower()


def test_topout_during_match_is_non_fatal(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    server.send(empty_tick(tick_no=1))
    server.send(Envelope(t="topout", p={"player": "own", "tick": 1, "score": 0}))
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "topout", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.result["exc"] is None
    assert run.result["exit_code"] == 0


def test_unknown_server_message_is_logged_not_fatal(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    server.send(Envelope(t="future_message_v6", p={"foo": "bar"}))
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.result["exit_code"] == 0
