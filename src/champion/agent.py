from __future__ import annotations

import logging
from typing import Callable, Optional

from . import protocol
from .board import DEFAULT_HEIGHT, DEFAULT_WIDTH, Board
from .net import Connection
from .protocol import Envelope
from .strategies.baseline import DEFAULT_WEIGHTS, Weights, choose_placement

log = logging.getLogger(__name__)

_HANDSHAKE_TIMEOUT = 30.0
_TICK_TIMEOUT = 5.0
_TICK_LOG_INTERVAL = 500

# Strategy signature: (board, kind, weights) -> (rot, x) or None.
StrategyFn = Callable[[Board, str, Weights], Optional[tuple[int, int]]]


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
        strategy: StrategyFn = choose_placement,
        weights: Weights = DEFAULT_WEIGHTS,
    ):
        self.host = host
        self.port = port
        self.agent_name = agent_name
        self.token = token
        self.strategy = strategy
        self.weights = weights
        self.match_id: str | None = None
        self.config_name: str | None = None
        self.tick_count = 0
        self.ping_count = 0
        self.locks_seen = 0
        self.lines_cleared = 0
        self.desync_count = 0
        self.last_score: int | None = None
        self.local_board = Board.empty(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self._planned_for_current_piece = False
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
                    "closing (ticks=%d pings=%d locks=%d cleared=%d desync=%d net.fallback=%d)",
                    self.tick_count,
                    self.ping_count,
                    self.locks_seen,
                    self.lines_cleared,
                    self.desync_count,
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
        # Adopt board geometry from the match config if present; default 12x20 otherwise.
        cfg = match_start.p.get("config") or {}
        if isinstance(cfg, dict):
            w = cfg.get("field_width", DEFAULT_WIDTH)
            h = cfg.get("field_height", DEFAULT_HEIGHT)
            if isinstance(w, int) and isinstance(h, int):
                self.local_board = Board.empty(w, h)
            else:
                log.warning(
                    "match_start.config has non-int field_width/field_height (w=%r h=%r); "
                    "keeping default %dx%d",
                    w, h, DEFAULT_WIDTH, DEFAULT_HEIGHT,
                )

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

        # Apply server delta first: SPEC §5.1 has gravity (step 1) before command
        # processing (step 2), so any info.state.own CRC in this same tick reflects
        # state after gravity. We must mirror that order here to compare apples to apples.
        delta = p.get("own_board_delta") or []
        if isinstance(delta, list) and delta:
            self.local_board = self.local_board.with_delta(delta)

        own = p.get("own") if isinstance(p.get("own"), dict) else {}
        score = own.get("score")
        if isinstance(score, int):
            self.last_score = score
        cleared = own.get("cleared_rows")
        if isinstance(cleared, int) and cleared > 0:
            self.lines_cleared += cleared
        locked = bool(own.get("locked"))
        if locked:
            self.locks_seen += 1
            self._planned_for_current_piece = False
            self._conn.send(protocol.info_query("state"))

        active = own.get("active_piece")
        if isinstance(active, dict) and not self._planned_for_current_piece:
            self._plan_for_active_piece(active)

        info = p.get("info")
        if isinstance(info, dict):
            self._verify_state(info.get("state"))

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

        if self.tick_count % _TICK_LOG_INTERVAL == 0:
            log.info(
                "tick=%s score=%s locks=%d cleared=%d desync=%d (net.fallback=%d)",
                p.get("tick"),
                score,
                self.locks_seen,
                self.lines_cleared,
                self.desync_count,
                self._conn.fallback_count,
            )

    def _plan_for_active_piece(self, active: dict) -> None:
        assert self._conn is not None
        kind = active.get("kind")
        cur_rot = active.get("rot")
        cur_x = active.get("x")
        if not (
            isinstance(kind, str)
            and isinstance(cur_rot, int)
            and isinstance(cur_x, int)
        ):
            log.warning("active_piece with unexpected fields: %r", active)
            return
        placement = self.strategy(self.local_board, kind, self.weights)
        if placement is None:
            log.warning(
                "no legal placement for %s at tick=%d; sending drop in place",
                kind,
                self.tick_count,
            )
            self._conn.send(protocol.action("drop"))
        else:
            target_rot, target_x = placement
            self._send_placement_actions(kind, cur_rot, cur_x, target_rot, target_x)
        self._planned_for_current_piece = True

    def _send_placement_actions(
        self, kind: str, cur_rot: int, cur_x: int, target_rot: int, target_x: int
    ) -> None:
        assert self._conn is not None
        cw = (target_rot - cur_rot) % 4
        ccw = (cur_rot - target_rot) % 4
        if cw <= ccw:
            for _ in range(cw):
                self._conn.send(protocol.action("rot_cw"))
        else:
            for _ in range(ccw):
                self._conn.send(protocol.action("rot_ccw"))
        dx = target_x - cur_x
        op = "right" if dx > 0 else "left"
        for _ in range(abs(dx)):
            self._conn.send(protocol.action(op))
        self._conn.send(protocol.action("drop"))
        log.debug(
            "queued %s: rot %d→%d, x %d→%d, drop",
            kind, cur_rot, target_rot, cur_x, target_x,
        )

    def _verify_state(self, state: object) -> None:
        if not isinstance(state, dict):
            return
        server_crc = state.get("own")
        if not isinstance(server_crc, str):
            return
        local_crc = self.local_board.crc32_state()
        if server_crc == local_crc:
            log.debug("state ok: %s", local_crc)
        else:
            self.desync_count += 1
            log.warning(
                "DESYNC #%d: server=%s local=%s tick=%d score=%s",
                self.desync_count,
                server_crc,
                local_crc,
                self.tick_count,
                self.last_score,
            )
