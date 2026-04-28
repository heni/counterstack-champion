import json

import pytest

from champion import protocol
from champion.protocol import Envelope, ProtocolError


def test_encode_ends_with_newline_and_utf8():
    raw = protocol.encode(Envelope(t="hello", p={"agent_name": "α"}))
    assert raw.endswith(b"\n")
    assert raw.count(b"\n") == 1
    obj = json.loads(raw)
    assert obj["t"] == "hello"
    assert obj["p"]["agent_name"] == "α"


def test_encode_omits_q_when_none():
    raw = protocol.encode(Envelope(t="ready", p={"config_name": "default"}))
    obj = json.loads(raw)
    assert "q" not in obj


def test_encode_includes_q_when_set():
    raw = protocol.encode(Envelope(t="action", q="own", p={"op": "drop"}))
    obj = json.loads(raw)
    assert obj["q"] == "own"


def test_decode_known_envelope():
    env = protocol.decode(b'{"t":"welcome","p":{"match_id":"m-1"}}')
    assert env.t == "welcome"
    assert env.p == {"match_id": "m-1"}
    assert env.q is None


def test_decode_with_q():
    env = protocol.decode(b'{"t":"action","q":"own","p":{"op":"left"}}')
    assert env.q == "own"


def test_decode_unknown_t_does_not_raise():
    env = protocol.decode(b'{"t":"future_message","p":{}}')
    assert env.t == "future_message"


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b'{"t":"x"',
        b"[1,2,3]",
        b'"just a string"',
        b'{"p":{}}',
        b'{"t":"","p":{}}',
        b'{"t":42,"p":{}}',
        b'{"t":"x"}',
        b'{"t":"x","p":[]}',
        b'{"t":"x","p":{},"q":7}',
    ],
)
def test_decode_invalid_raises(raw):
    with pytest.raises(ProtocolError):
        protocol.decode(raw)


def test_hello_builder():
    env = protocol.hello("alice", "tok-123")
    assert env.t == "hello" and env.q is None
    assert env.p == {
        "agent_name": "alice",
        "token": "tok-123",
        "protocol_version": protocol.PROTOCOL_VERSION,
    }


def test_ready_builder():
    env = protocol.ready("pentris-7")
    assert env.t == "ready" and env.q is None
    assert env.p == {"config_name": "pentris-7"}


@pytest.mark.parametrize("op", ["left", "right", "rot_cw", "rot_ccw", "drop", "noop"])
def test_action_builder_valid(op):
    env = protocol.action(op)
    assert env.t == "action" and env.q == "own"
    assert env.p == {"op": op}


def test_action_builder_invalid_op():
    with pytest.raises(ValueError):
        protocol.action("teleport")


@pytest.mark.parametrize("slot", [0, 1, 2])
def test_reorder_builder_valid(slot):
    env = protocol.reorder(slot)
    assert env.t == "reorder" and env.q == "opp"
    assert env.p == {"slot": slot}


def test_reorder_builder_invalid_slot():
    with pytest.raises(ValueError):
        protocol.reorder(3)


def test_pong_builder():
    env = protocol.pong(42)
    assert env.t == "pong" and env.q == "keepalive"
    assert env.p == {"nonce": 42}


@pytest.mark.parametrize("name", ["snapshot", "state", "scores", "match_time"])
def test_info_query_builder_valid(name):
    env = protocol.info_query(name)
    assert env.t == name and env.q == "info"
    assert env.p == {}


def test_info_query_invalid_name():
    with pytest.raises(ValueError):
        protocol.info_query("hidden_secrets")


@pytest.mark.parametrize(
    "env",
    [
        protocol.hello("a", "t"),
        protocol.ready("default"),
        protocol.action("drop"),
        protocol.reorder(2),
        protocol.pong(7),
        protocol.info_query("state"),
    ],
)
def test_roundtrip(env):
    raw = protocol.encode(env)
    assert raw.endswith(b"\n")
    decoded = protocol.decode(raw[:-1])
    assert decoded == env
