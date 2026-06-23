"""LLM integration: prompt construction and API calls via httpx2."""

from __future__ import annotations

import logging
from typing import Any

from ..models import LLMConfig, SmartInfo
from .prompts import build_batch_prompt, build_prompt, build_trend_prompt
from .providers import (
    AnthropicProvider,
    BaseLLMProvider,
    OpenAIProvider,
    get_provider,
)

__all__ = [
    "AnthropicProvider",
    "BaseLLMProvider",
    "OpenAIProvider",
    "call_llm",
    "call_llm_batch",
    "call_llm_trend",
]


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
    logging.debug("Calling LLM (provider=%s model=%s)", config.provider, config.model)
    provider = get_provider(config)
    user_prompt = build_prompt(
        fields,
        alerts_text,
        raw_data=raw_data,
        returncode=returncode,
        lang=config.lang,
    )
    return provider.call(user_prompt)


def call_llm_batch(
    entries: list[
        tuple[str, str, SmartInfo, list[Any], dict[str, Any] | None, int, str | None]
    ],
    config: LLMConfig,
) -> str | None:
    """Submit all disk results as a single batch to the LLM.

    Returns the LLM's analysis text, or ``None`` on any failure.
    """
    logging.debug(
        "Calling batch LLM with %d disk(s) (provider=%s model=%s)",
        len(entries),
        config.provider,
        config.model,
    )
    batch_config = config.model_copy(
        update={"system_prompt": config.batch_system_prompt}
    )
    provider = get_provider(batch_config)
    user_prompt = build_batch_prompt(entries, lang=config.lang)
    return provider.call(user_prompt)


def call_llm_trend(
    disk_name: str,
    disk_path: str,
    entries: list[tuple[str, SmartInfo]],
    config: LLMConfig,
) -> str | None:
    """Submit trend-analysis data for one disk to the LLM.

    Returns the LLM's analysis text, or ``None`` on any failure.
    """
    logging.debug(
        "Calling trend LLM for %s with %d data points (provider=%s model=%s)",
        disk_name,
        len(entries),
        config.provider,
        config.model,
    )
    provider = get_provider(config)
    user_prompt = build_trend_prompt(disk_name, disk_path, entries, lang=config.lang)
    return provider.call(user_prompt)
