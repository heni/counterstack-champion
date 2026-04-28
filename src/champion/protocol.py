from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 5

CLIENT_QUEUES = frozenset({"own", "opp", "info", "keepalive"})


class ProtocolError(ValueError):
    """Raised on malformed envelopes (bad JSON, missing/invalid t or p)."""


@dataclass(frozen=True)
class Envelope:
    t: str
    p: dict[str, Any]
    q: str | None = None


def encode(env: Envelope) -> bytes:
    obj: dict[str, Any] = {"t": env.t, "p": env.p}
    if env.q is not None:
        obj["q"] = env.q
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode(line: bytes) -> Envelope:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise ProtocolError(f"invalid JSON: {e}; line={line!r}") from e
    if not isinstance(obj, dict):
        raise ProtocolError(f"envelope is not a JSON object: {obj!r}")
    t = obj.get("t")
    if not isinstance(t, str) or not t:
        raise ProtocolError(f"missing or invalid 't': {obj!r}")
    p = obj.get("p")
    if not isinstance(p, dict):
        raise ProtocolError(f"missing or invalid 'p': {obj!r}")
    q = obj.get("q")
    if q is not None and not isinstance(q, str):
        raise ProtocolError(f"invalid 'q': {obj!r}")
    return Envelope(t=t, p=p, q=q)


def hello(agent_name: str, token: str = "") -> Envelope:
    return Envelope(
        t="hello",
        p={
            "agent_name": agent_name,
            "token": token,
            "protocol_version": PROTOCOL_VERSION,
        },
    )


def ready(config_name: str) -> Envelope:
    return Envelope(t="ready", p={"config_name": config_name})


_VALID_OPS = frozenset({"left", "right", "rot_cw", "rot_ccw", "drop", "noop"})


def action(op: str) -> Envelope:
    if op not in _VALID_OPS:
        raise ValueError(f"invalid op {op!r}; expected one of {sorted(_VALID_OPS)}")
    return Envelope(t="action", q="own", p={"op": op})


def reorder(slot: int) -> Envelope:
    if slot not in (0, 1, 2):
        raise ValueError(f"invalid slot {slot!r}; expected 0, 1, or 2")
    return Envelope(t="reorder", q="opp", p={"slot": slot})


def pong(nonce: int) -> Envelope:
    return Envelope(t="pong", q="keepalive", p={"nonce": nonce})


_INFO_QUERIES = frozenset({"snapshot", "state", "scores", "match_time"})


def info_query(name: str) -> Envelope:
    if name not in _INFO_QUERIES:
        raise ValueError(f"invalid info query {name!r}; expected one of {sorted(_INFO_QUERIES)}")
    return Envelope(t=name, q="info", p={})
