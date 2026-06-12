import argparse
import sys
from typing import NoReturn, Sequence

import argcomplete

from smartscan import __version__


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="A CLI tool that runs smartctl on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    subparsers = parser.add_subparsers(dest="command", title="commands")
    info_parser = subparsers.add_parser("info", help="Show project information")
    info_parser.set_defaults(func=_cmd_info)
    return parser


def _cmd_info(_args: argparse.Namespace) -> None:
    print("smartscan is ready.")


def _exit_help(parser: argparse.ArgumentParser) -> NoReturn:
    parser.print_help()
    sys.exit(1)


def main(argv: Sequence[str] | None = None) -> None:
    parser = create_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
    else:
        _exit_help(parser)
