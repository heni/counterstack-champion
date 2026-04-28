import argparse
import sys


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    print(f"endpoint={args.endpoint} log_level={args.log_level}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
