# Configuration

smartscan reads an optional TOML config file. When `--config` is not specified on
the command line, the first file found among the following is used:

1. `~/.config/smartscan/smartscan.toml` (XDG user config)
2. `/etc/smartscan/smartscan.toml` (system-wide config)

Pass `--config <path>` to use a specific file.

All keys shown below with their default values:

```toml
# ── Output ─────────────────────────────────────────────────────
# Output format: "table" or "json"
format = "table"

# Custom database path
db_path = "/var/lib/smartscan/smartscan.db"

# Custom log file path
log_file = "/var/log/smartscan/smartscan.log"

# Regex patterns to exclude disk devices by symlink name or resolved path.
# Applies to both `collect` and `lsblk` subcommands.
# Useful for filtering out optical drives, loop devices, ZFS zvols, etc.
# Example: exclude_patterns = ["BD-RE", '^/dev/(loop|zd)\d+']
exclude_patterns = []

# ── collect ────────────────────────────────────────────────────
[collect]
# Skip database writes (run once without saving)
no_save = false

# ── query ───────────────────────────────────────────────────────
[query]
# Restrict to records from this date (YYYY-MM-DD)
# since = "2025-01-01"

# Restrict to records until this date
# until = "2025-12-31"

# Show only records from the last N days (overrides `since`)
# last_days = 7

# ── lsblk ────────────────────────────────────────────────────
[lsblk]
# Restrict to specific /dev/disk/ source directories
# (by-id, by-path, by-diskseq; default: all when empty)
# source = ["by-id", "by-path"]

# ── Threshold alerts ────────────────────────────────────────────
[thresholds]
# Master switch: set to false to disable all threshold checks
enabled = true

# Alert if disk temperature exceeds this value (Celsius)
temperature_celsius = 50

# Alert if any sectors have been reallocated (surface defects)
reallocated_sector_ct = 0

# Alert if sectors are pending remap (often indicates instability)
current_pending_sector = 0

# Alert if sectors are uncorrectable offline (possible surface damage)
offline_uncorrectable = 0

# Alert if the reallocation event counter has increased
reallocated_event_count = 0

# Alert if UDMA CRC errors occur (typically a cabling or controller issue)
udma_crc_error_count = 0

# Alert if the ATA SMART error log contains entries
ata_smart_error_log_count = 0

# Alert if the disk has retried spinning up (motor/bearing wear)
spin_retry_count = 0

# Alert if head load/unload cycle count exceeds this value
# (600_000 is typical for many consumer hard drives; enterprise drives often rated higher)
load_cycle_count = 600_000

# ── LLM-based health analysis ──────────────────────────────────
[llm]
# Set to true to enable LLM analysis (requires API key)
enabled = false

# LLM API provider: "openai" (default) for OpenAI-compatible APIs,
# "anthropic" for Anthropic's native Messages API
provider = "openai"

# Full API URL, must include the path, e.g.,
#   https://api.openai.com/v1/chat/completions for OpenAI
#   https://api.anthropic.com/v1/messages for Anthropic
api_url = "https://api.openai.com/v1/chat/completions"

# Your API key (or set OPENAI_API_KEY / ANTHROPIC_API_KEY environment variable)
api_key = ""

# Model name as recognised by the API
model = "gpt-4o-mini"

# Maximum tokens in the model response (output limit, not input)
max_tokens = 4096

# HTTP request timeout in seconds
timeout = 120

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

See [LLM Examples](llm-examples.md) for provider-specific configuration snippets.
