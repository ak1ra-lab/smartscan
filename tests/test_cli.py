from smartscan.cli import create_parser


def test_create_parser_collect_subcommand() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect"])
    assert args.command == "collect"
    assert args.pattern == ".*"
    assert args.json is False
    assert args.no_save is False
    assert args.force_llm is False
    assert args.verbose is False


def test_create_parser_query_subcommand() -> None:
    parser = create_parser()
    args = parser.parse_args(["query"])
    assert args.command == "query"
    assert args.pattern == ".*"
    assert args.json is False
    assert args.verbose is False


def test_collect_with_pattern() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "WDC"])
    assert args.command == "collect"
    assert args.pattern == "WDC"


def test_collect_with_flags() -> None:
    parser = create_parser()
    args = parser.parse_args(
        ["--json", "collect", "--no-save", "--force-llm", "Samsung"]
    )
    assert args.command == "collect"
    assert args.json is True
    assert args.no_save is True
    assert args.force_llm is True
    assert args.pattern == "Samsung"


def test_collect_verbose_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "-v"])
    assert args.command == "collect"
    assert args.verbose is True


def test_collect_force_llm_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "--force-llm"])
    assert args.command == "collect"
    assert args.force_llm is True


def test_global_json_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["--json", "collect"])
    assert args.command == "collect"
    assert args.json is True


def test_query_with_dates() -> None:
    parser = create_parser()
    args = parser.parse_args(
        ["query", "--since", "2024-01-01", "--until", "2024-12-31"]
    )
    assert args.command == "query"
    assert args.since == "2024-01-01"
    assert args.until == "2024-12-31"


def test_query_verbose_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["query", "-v"])
    assert args.command == "query"
    assert args.verbose is True


def test_shared_global_args() -> None:
    parser = create_parser()
    args = parser.parse_args(["--db-path", "/tmp/test.db", "collect"])
    assert args.command == "collect"
    assert args.db_path == "/tmp/test.db"
