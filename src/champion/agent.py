from __future__ import annotations

import logging
from typing import Optional

from . import protocol
from .net import Connection
from .protocol import Envelope

log = logging.getLogger(__name__)

_HANDSHAKE_TIMEOUT = 30.0
_TICK_TIMEOUT = 5.0
_TICK_LOG_INTERVAL = 500


class HandshakeError(RuntimeError):
    pass


class Agent:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        agent_name: str = "champion",
        token: str = "",
    ):
        self.host = host
        self.port = port
        self.agent_name = agent_name
        self.token = token
        self.match_id: str | None = None
        self.config_name: str | None = None
        self.tick_count = 0
        self.ping_count = 0
        self._conn: Connection | None = None

    def run(self) -> int:
        log.info("connecting to %s:%s", self.host, self.port)
        self._conn = Connection(self.host, self.port)
        try:
            self._handshake()
            return self._match_loop()
        finally:
            if self._conn is not None:
                log.info(
                    "closing (ticks=%d pings=%d net.fallback=%d)",
                    self.tick_count,
                    self.ping_count,
                    self._conn.fallback_count,
                )
                self._conn.close()

    def _handshake(self) -> None:
        assert self._conn is not None
        self._conn.send(protocol.hello(self.agent_name, self.token))
        welcome = self._expect("welcome", timeout=_HANDSHAKE_TIMEOUT)
        self.match_id = welcome.p.get("match_id")
        raw_configs = welcome.p.get("available_configs") or []
        config_names = [
            c.get("name")
            for c in raw_configs
            if isinstance(c, dict) and isinstance(c.get("name"), str) and c.get("name")
        ]
        if not config_names:
            raise HandshakeError(
                f"welcome.p.available_configs has no usable name: {welcome.p}"
            )
        self.config_name = config_names[0]
        log.info(
            "welcome: match_id=%s configs=%s chosen=%s",
            self.match_id,
            config_names,
            self.config_name,
        )
        self._conn.send(protocol.ready(self.config_name))
        match_start = self._expect("match_start", timeout=_HANDSHAKE_TIMEOUT)
        log.info("match_start: seed=%s", match_start.p.get("seed"))

    def _expect(self, t: str, *, timeout: float) -> Envelope:
        env = self._receive(timeout=timeout)
        if env is None:
            raise HandshakeError(f"connection closed; expected {t}")
        if env.t == "error":
            raise HandshakeError(f"server error while expecting {t}: {env.p}")
        if env.t != t:
            raise HandshakeError(f"unexpected {env.t}; expected {t}: p={env.p}")
        return env

    def _receive(self, *, timeout: float) -> Optional[Envelope]:
        assert self._conn is not None
        return self._conn.recv(timeout=timeout)

    def _match_loop(self) -> int:
        while True:
            env = self._receive(timeout=_TICK_TIMEOUT)
            if env is None:
                log.warning("connection closed mid-match")
                return 1
            if env.t == "tick":
                self._handle_tick(env.p)
            elif env.t == "topout":
                log.info("topout: %s", env.p)
            elif env.t == "match_end":
                log.info("match_end: %s", env.p)
                return 0
            elif env.t == "error":
                log.warning("server error: %s", env.p)
            else:
                log.warning("unknown server message t=%s p=%s", env.t, env.p)

    def _handle_tick(self, p: dict) -> None:
        assert self._conn is not None
        self.tick_count += 1
        keepalive = p.get("keepalive")
        if isinstance(keepalive, dict):
            ping = keepalive.get("ping")
            if isinstance(ping, dict):
                nonce = ping.get("nonce")
                if isinstance(nonce, int) and not isinstance(nonce, bool):
                    self._conn.send(protocol.pong(nonce))
                    self.ping_count += 1
                    log.debug("pong nonce=%s", nonce)
                else:
                    log.warning("ignoring keepalive ping with invalid nonce: %r", nonce)
        own = p.get("own") if isinstance(p.get("own"), dict) else {}
        score = own.get("score")
        log.debug(
            "tick=%s score=%s frozen=%s",
            p.get("tick"),
            score,
            own.get("frozen"),
        )
        if self.tick_count % _TICK_LOG_INTERVAL == 0:
            log.info(
                "tick=%s score=%s pings=%d (net.fallback=%d)",
                p.get("tick"),
                score,
                self.ping_count,
                self._conn.fallback_count,
            )
