# smartscan

A CLI tool that runs `smartctl` on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.

## Highlights

- Collects SMART data via `smartctl --all --json` from `/dev/disk/by-id/ata-*` and `/dev/disk/by-id/nvme-*`.
- Displays results as Rich-styled tables with warnings for critical values.
- Maps disk devices to their `/dev/disk/` identifiers (by-id, by-path, by-diskseq) with a Rich tree view (`lsblk` subcommand).
- Stores historical data in SQLite for trend analysis (`query` subcommand).
- Supports JSON lines output for scripting.
- Configurable via TOML config file with Pydantic validation.
- Built with `uv`, `ruff`, `ty`, `pytest`, and `zensical`.
- CLI uses `argparse` and `argcomplete` for shell completion.

## Prerequisites

Install [smartmontools](https://www.smartmontools.org/) to provide the `smartctl` command:

```shell
# Debian/Ubuntu
apt install smartmontools

# RHEL/Fedora
dnf install smartmontools

# Arch
pacman -S smartmontools
```

## Install dependencies

```shell
# install from PyPI
uv tool install smartscan

# install from GitHub
uv tool install git+https://github.com/ak1ra-lab/smartscan.git
```

## Run the CLI

`smartscan collect` requires root to access disk devices via `smartctl`. Switch to a root shell first:

```shell
sudo -i
```

Once logged in as root, run commands normally:

```shell
smartscan collect
smartscan collect "WDC"
smartscan query --since 2024-01-01

smartscan --json collect
smartscan --json query --since 2024-01-01
```

`smartscan lsblk` maps block devices to their identifiers under `/dev/disk/`. It does not require root:

```shell
smartscan lsblk
smartscan lsblk "Samsung"
smartscan lsblk --source by-id
smartscan lsblk --source by-id --source by-diskseq
smartscan --json lsblk
```

Output example:

```
/dev/sda  [WDC WD40EFRX-68N32N0, 3.6 TiB]
├── by-id
│   ├── /dev/disk/by-id/ata-WDC_WD40EFRX-68N32N0_WD-WCC7K0123456
│   └── /dev/disk/by-id/wwn-0x50014ee26b123456
├── by-path
│   └── /dev/disk/by-path/pci-0000:00:17.0-ata-1
└── by-diskseq
    └── /dev/disk/by-diskseq/1
```

> `smartscan query` itself does not require root, but the default `db_path` resolves under the home directory of the user who ran `collect`. If you collected as root, the database lives under `/root/.local/share/smartscan/`, so query also needs root access to read it. Set a custom `db_path` in the config file to share the database across users.

## Configuration

smartscan reads an optional TOML config file at `~/.config/smartscan/smartscan.toml`. All subcommands, thresholds, and LLM settings are configurable.

See **[Configuration Reference](configuration.md)** for the full config file with all defaults, and **[LLM Examples](llm-examples.md)** for provider-specific snippets (DeepSeek, Anthropic, Ollama).

To force LLM analysis on healthy disks (no threshold alerts), use:

    sudo smartscan collect --force-llm

## Shell completion

smartscan uses [argcomplete](https://kislyuk.github.io/argcomplete/) for tab completion.

To enable per-shell, add the following line to your `~/.bashrc` (or equivalent shell config file):

```shell
eval "$(register-python-argcomplete smartscan)"
```

To enable system-wide completion for all argcomplete-based tools, run:

```shell
activate-global-python-argcomplete
```

See the [argcomplete documentation](https://kislyuk.github.io/argcomplete/) for zsh, fish, and tcsh support.

## Development

Clone the repository and install development dependencies:

```shell
git clone https://github.com/ak1ra-lab/smartscan.git
cd smartscan
uv sync --group dev
```

Common tasks are scripted as `just` recipes:

| Command           | What it does                                                           |
| ----------------- | ---------------------------------------------------------------------- |
| `just lint`       | Lint and format source code plus tests (`ruff check`, `ruff format`)   |
| `just typecheck`  | Run static type checking (`ty`) over `src/`                            |
| `just test`       | Run the pytest suite                                                   |
| `just coverage`   | Run tests with HTML coverage report                                    |
| `just build`      | Build the wheel and sdist                                              |
| `just docs-build` | Build the static docs site with Zensical                               |
| `just docs-serve` | Preview docs locally on the configured dev address                     |
| `just all`        | Run lint, typecheck, test, coverage, build, and docs-build in sequence |
