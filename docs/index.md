# smartscan

A CLI tool that runs `smartctl` on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.

## Highlights

- Collects SMART data via `smartctl --all --json` from `/dev/disk/by-id/ata-*` and `/dev/disk/by-id/nvme-*`.
- Displays results as Rich-styled tables with warnings for critical values.
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

> `smartscan query` itself does not require root, but the default `db_path` resolves under the home directory of the user who ran `collect`. If you collected as root, the database lives under `/root/.local/share/smartscan/`, so query also needs root access to read it. Set a custom `db_path` in the config file to share the database across users.

## Configuration

Create `~/.config/smartscan/smartscan.toml` (optional). All keys shown below with their default values:

```toml
# ── Output ─────────────────────────────────────────────────────
# Output format: "table" or "json"
format = "table"

# Skip database writes (run once without saving)
no_save = false

# Custom database path
db_path = "~/.local/share/smartscan/smartscan.db"

# Custom log file path
log_file = "~/.local/state/smartscan/smartscan.log"

# ── Threshold alerts ────────────────────────────────────────────
[thresholds]
enabled = true
temperature_celsius = 50
reallocated_sector_ct = 0
current_pending_sector = 0
offline_uncorrectable = 0
reallocated_event_count = 0
udma_crc_error_count = 0
ata_smart_error_log_count = 0
spin_retry_count = 0
load_cycle_count = 600_000

# ── LLM-based health analysis ──────────────────────────────────
[llm]
# Set to true to enable LLM analysis (requires API key)
enabled = false

# OpenAI-compatible API endpoint
endpoint = "https://api.openai.com/v1"

# Your API key (or set OPENAI_API_KEY environment variable)
api_key = ""

# Model name as recognised by the endpoint
model = "gpt-4o-mini"

# Maximum tokens in the model response (output limit, not input)
max_tokens = 500

# HTTP request timeout in seconds
timeout = 30

# Controls randomness: 0.0 = deterministic, higher = more creative
temperature = 0.3

# Seconds to wait between LLM calls when processing multiple disks (avoids rate limits)
delay = 0.0

# System prompt sent as the first message to guide the model's behaviour
system_prompt = """\
You are a hard drive health diagnostic expert analyzing SMART data.
Examine the provided SMART attributes and give a concise assessment:

1. Overall health status: HEALTHY / WARNING / CRITICAL
2. Key concerns with specific metric values (if any)
3. Recommended action (one sentence)

Be factual and conservative. Do not cause unnecessary alarm for borderline values.
If all metrics are within normal ranges, state the drive is healthy.
If you cannot make a definitive assessment, say so honestly.

Additionally, check the self-test log for the most recent long (extended)
self-test and compare its lifetime hours against the drive's total power-on
hours. If a significant portion of the drive's lifetime has passed since the
last long self-test, recommend running one."""
```

To force LLM analysis on healthy disks (no threshold alerts), use:

    sudo smartscan collect --force-llm

LLM example for DeepSeek (OpenAI-compatible),

```
# ── LLM example: DeepSeek (OpenAI-compatible) ──────────────────
[llm]
enabled = true
endpoint = "https://api.deepseek.com"
api_key = "sk-your-deepseek-key"
model = "deepseek-v4-flash"
max_tokens = 4096
timeout = 60
```

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
