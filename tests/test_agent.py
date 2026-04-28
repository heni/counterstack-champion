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


def _tick_with_active_piece(
    tick_no: int, kind: str, rot: int, x: int, y: int = 0
) -> Envelope:
    return Envelope(
        t="tick",
        p={
            "tick": tick_no,
            "duration_ns": 2_000_000,
            "own": {
                "op": None,
                "accepted": None,
                "active_piece": {"kind": kind, "rot": rot, "x": x, "y": y},
                "locked": False,
                "cleared_rows": 0,
                "score": 0,
                "frozen": False,
            },
            "opp": None,
            "info": None,
            "keepalive": None,
            "rejected": {"own": 0, "opp": 0, "info": 0, "keepalive": 0},
            "own_board_delta": [],
            "opp_board_delta": [],
            "my_queue": [kind, "I", "L"],
            "opp_queue": None,
        },
    )


def _drain_actions(server: MockServer, expected_count: int, timeout: float = 2.0) -> list:
    """Read N envelopes from the agent (actions or info-queries)."""
    return [server.recv(timeout=timeout) for _ in range(expected_count)]


def test_strategy_sends_drop_for_x_piece_at_spawn(server: MockServer) -> None:
    """X piece spawns at x=4 rot=0 on empty 12×20. Baseline picks (0, 0) (smallest x
    with same score). Agent must send: 4× left (4→0), drop. No rotations (X has 1
    canonical rot)."""
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    server.send(_tick_with_active_piece(1, "X", rot=0, x=4))
    actions = _drain_actions(server, 5)
    ops = [a.p["op"] for a in actions]
    assert all(a.t == "action" and a.q == "own" for a in actions)
    assert ops == ["left", "left", "left", "left", "drop"]
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.result["exit_code"] == 0


def test_strategy_no_rotation_no_shift_emits_only_drop(server: MockServer) -> None:
    """When current (rot, x) already matches target, agent emits a single drop."""
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    run.agent.strategy = lambda board, kind, weights: (0, 4)
    server.send(_tick_with_active_piece(1, "X", rot=0, x=4))
    actions = _drain_actions(server, 1)
    assert [a.p["op"] for a in actions] == ["drop"]
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)


def test_strategy_picks_shorter_rotation_path(server: MockServer) -> None:
    """L piece rot=0, target rot=3. CW path: 3 steps; CCW path: 1 step. Agent picks CCW."""
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )

    captured = []

    def fake_strategy(board, kind, weights):
        captured.append(kind)
        return (3, 5)  # target rot=3, x=5

    run.agent.strategy = fake_strategy
    server.send(_tick_with_active_piece(1, "L", rot=0, x=5))
    # rot 0→3: CCW is shorter (1 step). Then x=5 already; drop.
    actions = _drain_actions(server, 2)
    ops = [a.p["op"] for a in actions]
    assert ops == ["rot_ccw", "drop"]
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)


def test_lock_event_sends_state_query(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    # Tick reporting lock=true with no active_piece (transient between pieces).
    locked_tick = Envelope(
        t="tick",
        p={
            "tick": 1,
            "duration_ns": 2_000_000,
            "own": {
                "op": "drop",
                "accepted": True,
                "active_piece": None,
                "locked": True,
                "cleared_rows": 0,
                "score": 0,
                "frozen": False,
            },
            "opp": None,
            "info": None,
            "keepalive": None,
            "rejected": {"own": 0, "opp": 0, "info": 0, "keepalive": 0},
            "own_board_delta": [],
            "opp_board_delta": [],
            "my_queue": ["I", "L", "P"],
            "opp_queue": None,
        },
    )
    server.send(locked_tick)
    state_query = server.recv(timeout=2.0)
    assert state_query.t == "state"
    assert state_query.q == "info"
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.agent.locks_seen == 1


def test_desync_detected_when_server_crc_differs(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    bogus_tick = Envelope(
        t="tick",
        p={
            "tick": 1,
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
            "info": {"state": {"own": "crc32:deadbeef"}},
            "keepalive": None,
            "rejected": {"own": 0, "opp": 0, "info": 0, "keepalive": 0},
            "own_board_delta": [],
            "opp_board_delta": [],
            "my_queue": ["I", "L", "P"],
            "opp_queue": None,
        },
    )
    server.send(bogus_tick)
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.agent.desync_count == 1


def test_state_match_no_desync(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    # Empty 12×20 board CRC32 of '0'*240 — match agent's local_board.
    import zlib
    expected_crc = f"crc32:{zlib.crc32(b'0' * 240):08x}"
    tick = Envelope(
        t="tick",
        p={
            "tick": 1,
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
            "info": {"state": {"own": expected_crc}},
            "keepalive": None,
            "rejected": {"own": 0, "opp": 0, "info": 0, "keepalive": 0},
            "own_board_delta": [],
            "opp_board_delta": [],
            "my_queue": ["I", "L", "P"],
            "opp_queue": None,
        },
    )
    server.send(tick)
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.agent.desync_count == 0


def test_local_board_tracks_own_board_delta(server: MockServer) -> None:
    run = _spawn_agent(server.port)
    server.wait_for_connect()
    _drive_handshake(server)
    server.send(
        Envelope(t="match_start", p={"seed": 1, "config": {}, "initial_state": {}})
    )
    delta_tick = Envelope(
        t="tick",
        p={
            "tick": 1,
            "duration_ns": 2_000_000,
            "own": {
                "op": None, "accepted": None, "active_piece": None,
                "locked": False, "cleared_rows": 0, "score": 0, "frozen": False,
            },
            "opp": None, "info": None, "keepalive": None,
            "rejected": {"own": 0, "opp": 0, "info": 0, "keepalive": 0},
            "own_board_delta": [[0, 19, 1], [1, 19, 1]],
            "opp_board_delta": [],
            "my_queue": ["I", "L", "P"], "opp_queue": None,
        },
    )
    server.send(delta_tick)
    server.send(
        Envelope(
            t="match_end",
            p={"winner": None, "reason": "completed", "score": {"own": 0}},
        )
    )
    run.thread.join(timeout=3.0)
    assert run.agent.local_board.cells[19][0] is True
    assert run.agent.local_board.cells[19][1] is True
    assert run.agent.local_board.cells[19][2] is False
