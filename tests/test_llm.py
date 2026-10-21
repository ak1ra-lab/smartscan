from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from conftest import make_fields

from smartscan.llm import (
    AnthropicProvider,
    OpenAIProvider,
    call_llm,
)
from smartscan.llm.prompts import build_batch_prompt, build_prompt, build_trend_prompt
from smartscan.llm.providers import lang_instruction
from smartscan.models import LLMConfig
from smartscan.results import DiskEntry
from smartscan.thresholds import Alert


def _make_config(**overrides: str | int | float | bool) -> LLMConfig:
    defaults = {
        "enabled": True,
        "provider": "openai",
        "api_url": "https://api.openai.com/v1/chat/completions",
        "api_key": "sk-test-key",
        "model": "gpt-4o-mini",
        "max_tokens": 4096,
        "timeout": 120,
        "temperature": 0.3,
        "delay": 0.0,
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return LLMConfig.model_validate(defaults)


def _make_mock_response(json_body: dict) -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = json_body
    mock.status_code = 200
    return mock


class TestCallOpenAI:
    def test_builds_openai_request(self) -> None:
        fields = make_fields()
        alerts_text = "  - Temp 55 C exceeds 50 C"
        config = _make_config()

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "Drive is healthy."}}]})
            OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        call_kwargs = mock_post.call_args.kwargs
        assert mock_post.call_args.args[0] == "https://api.openai.com/v1/chat/completions"
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-test-key"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

        body = call_kwargs["json"]
        assert body["model"] == "gpt-4o-mini"
        assert body["max_tokens"] == 4096
        assert body["temperature"] == 0.3
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"

    def test_parses_openai_response(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config()

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "No issues detected."}}]})
            result = OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        assert result == "No issues detected."

    def test_skips_auth_header_when_no_key(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(api_key="")

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "ok"}}]})
            OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        assert "Authorization" not in mock_post.call_args.kwargs["headers"]

    def test_returns_none_on_http_error(self) -> None:
        import httpx2

        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config()

        with patch("httpx2.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_response.raise_for_status.side_effect = httpx2.HTTPStatusError(
                "500 error", request=MagicMock(), response=mock_response
            )
            mock_post.return_value = mock_response

            result = OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        assert result is None

    def test_logs_warning_when_anthropic_api_url(self, caplog) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(api_url="https://api.anthropic.com/v1/messages")

        with caplog.at_level(logging.WARNING), patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "ok"}}]})
            OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        assert "api_url does not appear to match" in caplog.text

    def test_logs_warning_when_messages_path(self, caplog) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            api_url="https://my-proxy.example.com/v1/messages",
        )

        with caplog.at_level(logging.WARNING), patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "ok"}}]})
            OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        assert "api_url does not appear to match" in caplog.text

    def test_no_warning_when_api_url_matches(self, caplog) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config()

        with caplog.at_level(logging.WARNING), patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "ok"}}]})
            OpenAIProvider(config).call(build_prompt(fields, alerts_text))

        assert "api_url does not appear to match" not in caplog.text


class TestCallAnthropic:
    def test_builds_anthropic_request(self) -> None:
        fields = make_fields()
        alerts_text = "  - Temp 55 C exceeds 50 C"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
            model="claude-sonnet-4-20250514",
        )

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "Drive is healthy."}]})
            AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        call_kwargs = mock_post.call_args.kwargs
        assert mock_post.call_args.args[0] == "https://api.anthropic.com/v1/messages"
        assert call_kwargs["headers"]["x-api-key"] == "sk-test-key"
        assert call_kwargs["headers"]["anthropic-version"] == "2023-06-01"
        assert call_kwargs["headers"]["Content-Type"] == "application/json"

        body = call_kwargs["json"]
        assert body["model"] == "claude-sonnet-4-20250514"
        assert body["max_tokens"] == 4096
        assert body["temperature"] == 0.3
        assert body["system"] is not None
        assert body["messages"][0]["role"] == "user"

    def test_parses_anthropic_response(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
        )

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "All clear."}]})
            result = AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert result == "All clear."

    def test_skips_auth_header_when_no_key(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
            api_key="",
        )

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "ok"}]})
            AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert "x-api-key" not in mock_post.call_args.kwargs["headers"]

    def test_logs_warning_when_openai_api_url(self, caplog) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.openai.com/v1/chat/completions",
        )

        with caplog.at_level(logging.WARNING), patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "ok"}]})
            AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert "api_url does not appear to match" in caplog.text

    def test_logs_warning_when_chat_completions_path(self, caplog) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://my-proxy.example.com/v1/chat/completions",
        )

        with caplog.at_level(logging.WARNING), patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "ok"}]})
            AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert "api_url does not appear to match" in caplog.text

    def test_no_warning_when_api_url_matches(self, caplog) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
        )

        with caplog.at_level(logging.WARNING), patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "ok"}]})
            AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert "api_url does not appear to match" not in caplog.text

    def test_returns_none_on_http_error(self) -> None:
        import httpx2

        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
        )

        with patch("httpx2.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_response.raise_for_status.side_effect = httpx2.HTTPStatusError(
                "500 error", request=MagicMock(), response=mock_response
            )
            mock_post.return_value = mock_response

            result = AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert result is None

    def test_handles_thinking_blocks(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
        )

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response(
                {
                    "content": [
                        {"type": "thinking", "thinking": "Analysing..."},
                        {"type": "text", "text": "Drive looks good."},
                    ]
                }
            )
            result = AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert result == "Drive looks good."

    def test_handles_content_key_instead_of_text(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://ollama.example.com/v1/messages",
        )

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response(
                {"content": [{"type": "text", "content": "Compat format result"}]}
            )
            result = AnthropicProvider(config).call(build_prompt(fields, alerts_text))

        assert result == "Compat format result"


class TestLangInstruction:
    def test_zh_alias(self) -> None:
        assert lang_instruction("zh") == lang_instruction("zh-CN")

    def test_unsupported_language_returns_none(self) -> None:
        assert lang_instruction("fr") is None


class TestBuildPrompt:
    def test_none_numeric_field_renders_as_na(self) -> None:
        fields = make_fields(data_written_tib=None)

        prompt = build_prompt(fields, "  (none)")

        assert "None" not in prompt
        assert "Data Written:         N/A" in prompt

    def test_na_formatted_fields_render_without_units(self) -> None:
        fields = make_fields(
            available_spare_percent="N/A",
            endurance_used_percent="N/A",
            power_on_time="N/A",
            temperature="N/A",
        )

        prompt = build_prompt(fields, "  (none)")

        assert "N/A%" not in prompt
        assert "N/A hours" not in prompt
        assert "N/A°C" not in prompt

    def test_includes_complete_extracted_fields(self) -> None:
        fields = make_fields(serial_number="SERIAL123", interface_speed="6.0 Gb/s")

        prompt = build_prompt(fields, "  (none)")

        assert "Complete extracted fields:" in prompt
        assert "serial_number: SERIAL123" in prompt
        assert "interface_speed: 6.0 Gb/s" in prompt

    def test_includes_complete_raw_smartctl_json(self) -> None:
        raw_data = {
            "ata_smart_attributes": {
                "table": [
                    {"id": 5, "name": "Reallocated_Sector_Ct", "raw": {"value": 3, "string": "3"}},
                    {"id": 197, "name": "Current_Pending_Sector", "raw": {"value": 0, "string": "0"}},
                ]
            }
        }

        prompt = build_prompt(make_fields(), "  (none)", raw_data=raw_data)

        assert "Complete smartctl JSON (all attributes and logs):" in prompt
        assert '"name": "Reallocated_Sector_Ct"' in prompt
        assert '"id": 197' in prompt


class TestBuildBatchPrompt:
    def test_includes_disk_details_and_errors(self) -> None:
        entry = DiskEntry(
            disk_name="sda",
            disk_path="/dev/sda",
            fields=make_fields(model_name="Test Model"),
            alerts=[
                Alert(
                    field="temperature",
                    level="warning",
                    message="temperature: 55 (threshold: 50)",
                )
            ],
            data={},
            returncode=4,
        )

        prompt = build_batch_prompt([entry])

        assert "## Disk: sda (Test Model)" in prompt
        assert "Path: /dev/sda" in prompt
        assert "- temperature: 55 (threshold: 50)" in prompt
        assert "smartctl errors:" in prompt
        assert "Bit 2" in prompt

    def test_skips_entries_without_fields(self) -> None:
        entry = DiskEntry("sdb", "/dev/sdb", None, [], None, 1)

        prompt = build_batch_prompt([entry])

        assert "0 disk devices" in prompt
        assert "sdb" not in prompt

    def test_includes_complete_fields_and_raw_json(self) -> None:
        entry = DiskEntry(
            disk_name="sda",
            disk_path="/dev/sda",
            fields=make_fields(serial_number="SERIAL123"),
            alerts=[],
            data={
                "ata_smart_attributes": {
                    "table": [
                        {"id": 197, "name": "Current_Pending_Sector", "raw": {"value": 2, "string": "2"}},
                    ]
                }
            },
            returncode=0,
        )

        prompt = build_batch_prompt([entry])

        assert "Complete extracted fields:" in prompt
        assert "serial_number: SERIAL123" in prompt
        assert "Complete smartctl JSON (all attributes and logs):" in prompt
        assert '"name": "Current_Pending_Sector"' in prompt


class TestBuildTrendPrompt:
    def test_includes_latest_complete_fields(self) -> None:
        entries = [
            ("2026-01-01T00:00:00Z", make_fields(firmware_version="OLD-FW")),
            ("2026-01-02T00:00:00Z", make_fields(firmware_version="NEW-FW")),
        ]

        prompt = build_trend_prompt("sda", "/dev/sda", entries)

        assert "Latest record — complete extracted fields:" in prompt
        assert "firmware_version: NEW-FW" in prompt
        assert "firmware_version: OLD-FW" not in prompt


class TestCallLLMDispatcher:
    def test_dispatches_to_openai_by_default(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config()

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"choices": [{"message": {"content": "OpenAI result"}}]})
            result = call_llm(fields, alerts_text, config)

        assert result == "OpenAI result"
        assert mock_post.call_args.args[0].endswith("/chat/completions")

    def test_dispatches_to_anthropic_when_provider_is_anthropic(self) -> None:
        fields = make_fields()
        alerts_text = "  (none)"
        config = _make_config(
            provider="anthropic",
            api_url="https://api.anthropic.com/v1/messages",
        )

        with patch("httpx2.post") as mock_post:
            mock_post.return_value = _make_mock_response({"content": [{"type": "text", "text": "Anthropic result"}]})
            result = call_llm(fields, alerts_text, config)

        assert result == "Anthropic result"
        assert mock_post.call_args.args[0].endswith("/messages")


class TestExtractAnthropicText:
    _provider = AnthropicProvider(_make_config(provider="anthropic", api_url="https://api.anthropic.com/v1/messages"))

    def test_standard_format(self) -> None:
        result = self._provider.parse_response({"content": [{"type": "text", "text": "All clear."}]})
        assert result == "All clear."

    def test_fallback_to_content_key(self) -> None:
        result = self._provider.parse_response({"content": [{"type": "text", "content": "Compat format"}]})
        assert result == "Compat format"

    def test_skips_thinking_blocks(self) -> None:
        result = self._provider.parse_response(
            {
                "content": [
                    {"type": "thinking", "thinking": "Let me analyse..."},
                    {"type": "text", "text": "Drive is healthy."},
                ]
            }
        )
        assert result == "Drive is healthy."

    def test_non_text_block_no_type_falls_through(self) -> None:
        result = self._provider.parse_response({"content": [{"content": "No type field"}]})
        assert result == "No type field"

    def test_missing_content_key_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="no content blocks"):
            self._provider.parse_response({"id": "msg_123"})

    def test_empty_content_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="no content blocks"):
            self._provider.parse_response({"content": []})

    def test_text_key_takes_priority_over_content_key(self) -> None:
        result = self._provider.parse_response({"content": [{"text": "primary", "content": "fallback"}]})
        assert result == "primary"
