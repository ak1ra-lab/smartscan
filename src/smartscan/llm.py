"""LLM integration: prompt construction and API calls via httpx2."""

from __future__ import annotations

import abc
import json
import logging
import os
from typing import Any

from .fields import (
    BASIC_PROMPT_FIELDS,
    CRITICAL_PROMPT_FIELDS,
    SECONDARY_PROMPT_FIELDS,
    get_field,
)
from .models import LLMConfig, SmartInfo
from .smartctl import smartctl_error_lines


def _build_prompt(
    fields: SmartInfo,
    alerts_text: str,
    raw_data: dict[str, Any] | None = None,
    returncode: int | None = None,
) -> str:
    lines = ["SMART Data for Analysis:", ""]

    for f in BASIC_PROMPT_FIELDS:
        value = get_field(fields, f.key)
        label = f.prompt_label or f.key
        if f.key == "user_capacity_gib" and value is None:
            lines.append(f"  {label}:      N/A")
        elif f.format_label:
            lines.append(f"  {label}: {f.format_label.format(value=value)}")
        else:
            lines.append(f"  {label}: {value}")

    lines.append("")
    lines.append("  Critical Attributes:")
    for f in CRITICAL_PROMPT_FIELDS:
        lines.append(f"    {f.prompt_label or f.key}:     {get_field(fields, f.key)}")

    lines.append("")
    lines.append("  Secondary Attributes:")
    for f in SECONDARY_PROMPT_FIELDS:
        lines.append(
            f"    {f.prompt_label or f.key}:         {get_field(fields, f.key)}"
        )

    if raw_data:
        raw_json = json.dumps(raw_data, indent=2, ensure_ascii=False)
        lines.extend(["", "Raw smartctl JSON:", "```json", raw_json, "```"])

    lines.extend(["", "Triggered Alerts:", alerts_text])

    if returncode is not None and returncode != 0:
        lines.append("")
        lines.extend(smartctl_error_lines(returncode))

    return "\n".join(lines)


def _do_request(
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: int,
) -> dict[str, Any] | None:
    """Send an HTTP POST and return the parsed JSON response.

    Returns ``None`` on any failure after logging the error.
    """
    import httpx2

    try:
        response = httpx2.post(url, headers=headers, json=body, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except httpx2.HTTPStatusError as exc:
        logging.error(
            "LLM API returned HTTP %d: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx2.RequestError as exc:
        logging.error("LLM API request failed: %s", exc)
    except Exception:
        logging.exception("Unexpected error during LLM call")

    return None


# ── provider abstraction ───────────────────────────────────────────────


class BaseLLMProvider(abc.ABC):
    """Template method for calling an LLM provider's API.

    Subclasses declare provider-specific behaviour through abstract
    methods and the class-level :attr:`_rival_indicators` list.
    """

    _rival_indicators: list[str] = []

    def __init__(self, config: LLMConfig) -> None:
        self._config = config

    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

    @abc.abstractmethod
    def build_body(self, user_prompt: str) -> dict[str, Any]: ...

    @abc.abstractmethod
    def build_headers(self) -> dict[str, str]: ...

    @abc.abstractmethod
    def parse_response(self, data: dict[str, Any]) -> str: ...

    def check_url_mismatch(self) -> None:
        indicators = self._rival_indicators
        if not indicators:
            return

        url = self._config.api_url
        url_lower = url.lower()

        suspicious = any(i in url_lower for i in indicators if "/" not in i) or any(
            url.rstrip("/").endswith(i) for i in indicators if "/" in i
        )

        if suspicious:
            logging.warning(
                "LLM provider is '%s' but api_url does not appear to match (%s) "
                "— ensure this is intentional",
                self.provider_name,
                url,
            )

    def call(
        self,
        fields: SmartInfo,
        alerts_text: str,
        raw_data: dict[str, Any] | None = None,
        returncode: int | None = None,
    ) -> str | None:
        self.check_url_mismatch()
        user_prompt = _build_prompt(
            fields, alerts_text, raw_data=raw_data, returncode=returncode
        )

        body = self.build_body(user_prompt)
        headers = self.build_headers()

        data = _do_request(self._config.api_url, headers, body, self._config.timeout)
        if data is None:
            return None

        try:
            return self.parse_response(data)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logging.error("Unexpected LLM API response format: %s", exc)
            return None


class OpenAIProvider(BaseLLMProvider):
    """OpenAI-compatible Chat Completions provider."""

    provider_name = "openai"
    _rival_indicators = ["anthropic", "/messages"]

    def build_body(self, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            "messages": [
                {"role": "system", "content": self._config.system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

    def build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = os.environ.get("OPENAI_API_KEY", "") or self._config.api_key
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def parse_response(self, data: dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Messages API provider."""

    provider_name = "anthropic"
    _rival_indicators = ["openai", "/chat/completions"]

    def build_body(self, user_prompt: str) -> dict[str, Any]:
        return {
            "model": self._config.model,
            "max_tokens": self._config.max_tokens,
            "temperature": self._config.temperature,
            "system": self._config.system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }

    def build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        api_key = os.environ.get("ANTHROPIC_API_KEY", "") or self._config.api_key
        if api_key:
            headers["x-api-key"] = api_key
        return headers

    def parse_response(self, data: dict[str, Any]) -> str:
        """Extract the first text content block from an Anthropic response.

        Tries ``text`` then ``content`` key in each content block.
        Skips non-text blocks (e.g. ``thinking``).
        """
        content_blocks: list[dict[str, Any]] = data.get("content", [])
        if not content_blocks:
            raise ValueError("no content blocks in response")

        for block in content_blocks:
            block_type = block.get("type", "")
            if block_type and block_type != "text":
                continue
            for key in ("text", "content"):
                if key in block:
                    return block[key]

        raise ValueError("no text content block found in response")


# ── provider registry ───────────────────────────────────────────────


_PROVIDERS: dict[str, type[BaseLLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
}


def _get_provider(config: LLMConfig) -> BaseLLMProvider:
    cls = _PROVIDERS.get(config.provider, OpenAIProvider)
    return cls(config)


def call_llm(
    fields: SmartInfo,
    alerts_text: str,
    config: LLMConfig,
    raw_data: dict[str, Any] | None = None,
    returncode: int | None = None,
) -> str | None:
    """Call the configured LLM provider's API.

    Returns the LLM's analysis text, or ``None`` on any failure.
    """
    return _get_provider(config).call(
        fields, alerts_text, raw_data=raw_data, returncode=returncode
    )
