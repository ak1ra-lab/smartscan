# LLM Examples

## LLM invocation modes

The `collect` subcommand supports three LLM modes via `--llm`:

| Flag | Behaviour |
|---|---|
| `--llm all` | Per-disk LLM analysis on every disk, regardless of alerts |
| `--llm summary` | Single batch LLM call across all collected disks |
| `--llm off` | Skip LLM entirely |

Without the `--llm` flag, the default behaviour is config-driven: per-disk analysis only for disks that triggered threshold alerts.

The `query` subcommand supports trend analysis via `--trend`, which sends
time-series data to the LLM for each disk after compaction:

```
smartscan query --last-days 30 --trend
```

Set `lang = "zh"` in `[llm]` to receive Chinese (简体中文) responses from any
LLM mode (per-disk, batch summary, trend analysis).

## [OpenAI](https://developers.openai.com/api/reference/overview)

```toml
[llm]
enabled = true
provider = "openai"
api_url = "https://api.openai.com/v1/chat/completions"
api_key = "sk-your-openai-key"
model = "deepseek-v4-flash"
max_tokens = 4096
timeout = 60
```

## [Anthropic](https://platform.claude.com/docs/en/api/overview)

```toml
[llm]
enabled = true
provider = "anthropic"
api_url = "https://api.anthropic.com/v1/messages"
api_key = "sk-ant-..."
model = "claude-sonnet-4-20250514"
max_tokens = 4096
timeout = 60
```

## [DeepSeek](https://api-docs.deepseek.com/zh-cn/)

DeepSeek OpenAI-compatible (with Chinese responses):

```toml
[llm]
enabled = true
provider = "openai"
api_url = "https://api.deepseek.com/chat/completions"
api_key = "sk-your-deepseek-key"
model = "deepseek-v4-flash"
max_tokens = 4096
timeout = 60
lang = "zh"
```

DeepSeek Anthropic-compatible,

```toml
[llm]
enabled = true
provider = "anthropic"
api_url = "https://api.deepseek.com/anthropic/messages"
api_key = "sk-your-deepseek-key"
model = "deepseek-v4-pro"
max_tokens = 4096
timeout = 60
```

## Local Ollama / LM Studio (no API key needed)

```toml
[llm]
enabled = true
provider = "openai"
api_url = "http://localhost:11434/v1/chat/completions"
model = "llama3"
```

For Anthropic-compatible local endpoints (Ollama ≥ 0.5):

```toml
[llm]
enabled = true
provider = "anthropic"
api_url = "http://localhost:11434/v1/messages"
model = "qwen3:8b"
```
