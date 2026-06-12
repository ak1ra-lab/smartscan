# Getting Started

## Prerequisites

Install [smartmontools](https://www.smartmontools.org/) to provide the `smartctl` command:

```bash
# Debian/Ubuntu
apt install smartmontools
# RHEL/Fedora
dnf install smartmontools
# Arch
pacman -S smartmontools
```

## Install dependencies

```bash
# install from PyPI
uv tool install smartscan

# install from GitHub
uv tool install git+https://github.com/ak1ra-lab/smartscan.git

# development install (clone first)
uv sync --group dev
```

## Run the CLI

Most commands require root to access SMART data:

```bash
sudo smartscan collect
```

Collect with a name filter:

```bash
sudo smartscan collect "WDC"
```

Query historical records:

```bash
smartscan query --since 2024-01-01
```

JSON output for scripting:

```bash
sudo smartscan --json collect
smartscan --json query --since 2024-01-01
```

## Configuration

Create `~/.config/smartscan/smartscan.toml` (optional):

```toml
# Output format: "table" or "json"
format = "table"
# Skip database writes
no_save = false
# Custom database path
db_path = "~/.local/share/smartscan/smartscan.db"
# Custom log path
log_file = "~/.local/state/smartscan/smartscan.log"
```

## Shell completion

```bash
eval "$(register-python-argcomplete smartscan)"
```

## Common tasks

```bash
just all
just lint
just typecheck
just test
just docs-build
```
