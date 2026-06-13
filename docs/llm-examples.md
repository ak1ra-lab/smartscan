# LLM Examples

## DeepSeek (OpenAI-compatible)

```toml
[llm]
enabled = true
provider = "openai"
api_url = "https://api.deepseek.com/chat/completions"
api_key = "sk-your-deepseek-key"
model = "deepseek-v4-flash"
max_tokens = 4096
timeout = 60
```

## DeepSeek (Anthropic-compatible)

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

## Anthropic

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
