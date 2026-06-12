from smartscan.cli import create_parser


def test_info_command() -> None:
    parser = create_parser()
    args = parser.parse_args(["info"])

    assert args.command == "info"
