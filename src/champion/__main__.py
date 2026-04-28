from __future__ import annotations

import argparse
import logging
import sys

from .agent import Agent, HandshakeError


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="champion",
        description="CounterStack qualification arena agent.",
    )
    parser.add_argument("endpoint", help="Server endpoint as host:port")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Path to log file (default: stderr)",
    )
    parser.add_argument("--agent-name", default="champion")
    parser.add_argument("--token", default="")
    return parser


def parse_endpoint(value: str) -> tuple[str, int]:
    if ":" not in value:
        raise ValueError(f"endpoint must be host:port, got: {value!r}")
    host, port_s = value.rsplit(":", 1)
    if not host:
        raise ValueError(f"missing host in endpoint: {value!r}")
    try:
        port = int(port_s)
    except ValueError as e:
        raise ValueError(f"invalid port in endpoint: {value!r}") from e
    if port <= 0 or port > 65535:
        raise ValueError(f"port out of range: {port}")
    return host, port


def _setup_logging(level: str, log_file: str | None) -> None:
    fmt = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s %(message)s"
    datefmt = "%H:%M:%S"
    handlers: list[logging.Handler]
    if log_file:
        handlers = [logging.FileHandler(log_file)]
    else:
        handlers = [logging.StreamHandler(sys.stderr)]
    logging.basicConfig(
        level=getattr(logging, level),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        host, port = parse_endpoint(args.endpoint)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    _setup_logging(args.log_level, args.log_file)
    log = logging.getLogger("champion")
    agent = Agent(host, port, agent_name=args.agent_name, token=args.token)
    try:
        return agent.run()
    except HandshakeError as e:
        log.error("handshake failed: %s", e)
        return 1
    except OSError as e:
        log.error("connection failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
