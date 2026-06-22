from smartscan.cli import create_parser


def test_create_parser_collect_subcommand() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect"])
    assert args.command == "collect"
    assert args.pattern == ".*"
    assert args.json is False
    assert args.no_save is False
    assert args.llm is None
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
        ["--json", "collect", "--no-save", "--llm", "all", "Samsung"]
    )
    assert args.command == "collect"
    assert args.json is True
    assert args.no_save is True
    assert args.llm == "all"
    assert args.pattern == "Samsung"


def test_collect_verbose_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "-v"])
    assert args.command == "collect"
    assert args.verbose is True


def test_collect_llm_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "--llm", "all"])
    assert args.command == "collect"
    assert args.llm == "all"


def test_collect_llm_summary() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "--llm", "summary"])
    assert args.llm == "summary"


def test_collect_llm_off() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "--llm", "off"])
    assert args.llm == "off"


def test_collect_notify_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["collect", "--notify"])
    assert args.notify is True


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


def test_lsblk_basic() -> None:
    parser = create_parser()
    args = parser.parse_args(["lsblk"])
    assert args.command == "lsblk"
    assert args.pattern == ".*"
    assert args.lsblk_source is None
    assert args.exclude_patterns == []


def test_lsblk_with_pattern() -> None:
    parser = create_parser()
    args = parser.parse_args(["lsblk", "WDC"])
    assert args.command == "lsblk"
    assert args.pattern == "WDC"


def test_lsblk_with_source() -> None:
    parser = create_parser()
    args = parser.parse_args(["lsblk", "--source", "by-id"])
    assert args.command == "lsblk"
    assert args.lsblk_source == ["by-id"]


def test_lsblk_with_multiple_sources() -> None:
    parser = create_parser()
    args = parser.parse_args(["lsblk", "--source", "by-id", "--source", "by-path"])
    assert args.command == "lsblk"
    assert args.lsblk_source == ["by-id", "by-path"]


def test_lsblk_with_json() -> None:
    parser = create_parser()
    args = parser.parse_args(["--json", "lsblk"])
    assert args.command == "lsblk"
    assert args.json is True


def test_lsblk_with_pattern_and_source() -> None:
    parser = create_parser()
    args = parser.parse_args(["lsblk", "--source", "by-diskseq", "Samsung"])
    assert args.command == "lsblk"
    assert args.pattern == "Samsung"
    assert args.lsblk_source == ["by-diskseq"]


def test_lsblk_with_exclude() -> None:
    parser = create_parser()
    args = parser.parse_args(["--exclude", "^/dev/loop", "lsblk"])
    assert args.command == "lsblk"
    assert args.exclude_patterns == ["^/dev/loop"]


def test_lsblk_with_multiple_excludes() -> None:
    parser = create_parser()
    args = parser.parse_args(
        ["--exclude", "^/dev/loop", "--exclude", "^/dev/zd", "lsblk"]
    )
    assert args.exclude_patterns == ["^/dev/loop", "^/dev/zd"]


def test_lsblk_with_exclude_and_source() -> None:
    parser = create_parser()
    args = parser.parse_args(
        ["--exclude", "^/dev/loop", "lsblk", "--source", "by-id", "nvme"]
    )
    assert args.command == "lsblk"
    assert args.pattern == "nvme"
    assert args.lsblk_source == ["by-id"]
    assert args.exclude_patterns == ["^/dev/loop"]


def test_collect_with_exclude() -> None:
    parser = create_parser()
    args = parser.parse_args(["--exclude", "BD-RE", "collect"])
    assert args.command == "collect"
    assert args.exclude_patterns == ["BD-RE"]


def test_collect_with_multiple_excludes() -> None:
    parser = create_parser()
    args = parser.parse_args(
        ["--exclude", "BD-RE", "--exclude", "^/dev/loop", "collect"]
    )
    assert args.exclude_patterns == ["BD-RE", "^/dev/loop"]


def test_query_with_last_days() -> None:
    parser = create_parser()
    args = parser.parse_args(["query", "--last-days", "7"])
    assert args.command == "query"
    assert args.last_days == 7


def test_prune_subcommand_basic() -> None:
    parser = create_parser()
    args = parser.parse_args(["prune"])
    assert args.command == "prune"
    assert args.pattern == ".*"
    assert args.prune_window == 30
    assert args.dry_run is False
    assert args.force is False


def test_prune_with_pattern() -> None:
    parser = create_parser()
    args = parser.parse_args(["prune", "WDC"])
    assert args.command == "prune"
    assert args.pattern == "WDC"


def test_prune_with_window() -> None:
    parser = create_parser()
    args = parser.parse_args(["prune", "--window", "60"])
    assert args.command == "prune"
    assert args.prune_window == 60


def test_prune_dry_run() -> None:
    parser = create_parser()
    args = parser.parse_args(["prune", "--dry-run"])
    assert args.command == "prune"
    assert args.dry_run is True


def test_prune_force() -> None:
    parser = create_parser()
    args = parser.parse_args(["prune", "--force"])
    assert args.command == "prune"
    assert args.force is True


def test_prune_short_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["prune", "-f"])
    assert args.command == "prune"
    assert args.force is True


def test_query_no_compact_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["query", "--no-compact"])
    assert args.command == "query"
    assert args.no_compact is True


def test_query_compact_window_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["query", "--compact-window", "15"])
    assert args.command == "query"
    assert args.compact_window == 15


def test_query_trend_flag() -> None:
    parser = create_parser()
    args = parser.parse_args(["query", "--trend"])
    assert args.command == "query"
    assert args.trend is True


def test_query_default_compact_enabled() -> None:
    parser = create_parser()
    args = parser.parse_args(["query"])
    assert args.no_compact is False
