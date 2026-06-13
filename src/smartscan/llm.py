"""LLM integration: prompt construction and API calls via httpx2."""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import LLMConfig, SmartInfo


def _build_prompt(
    fields: SmartInfo, alerts_text: str, raw_data: dict[str, Any] | None = None
) -> str:
    lines = [
        "SMART Data for Analysis:",
        "",
        f"  Model Family:  {fields['model_family']}",
        f"  Model Name:    {fields['model_name']}",
        f"  SMART Status:  {fields['smart_status']}",
        f"  Capacity:      {fields['user_capacity_gib']} GiB"
        if fields["user_capacity_gib"] is not None
        else "  Capacity:      N/A",
        f"  Rotation:      {fields['rotation_rate_display']}",
        f"  Power On Time: {fields['power_on_time']} hours",
        f"  Power Cycles:  {fields['power_cycle_count']}",
        f"  Temperature:   {fields['temperature']} C",
        "",
        "  Critical Attributes:",
        f"    Reallocated Sectors:     {fields['reallocated_sector_ct']}",
        f"    Current Pending Sectors: {fields['current_pending_sector']}",
        f"    Offline Uncorrectable:   {fields['offline_uncorrectable']}",
        f"    Reallocated Event Count: {fields['reallocated_event_count']}",
        f"    ATA Error Log Count:     {fields['ata_smart_error_log']}",
        f"    Self-Test Status:        {fields['self_test_status']}",
        "",
        "  Secondary Attributes:",
        f"    UDMA CRC Errors:         {fields['udma_crc_error_count']}",
        f"    Raw Read Error Rate:     {fields['raw_read_error_rate']}",
        f"    Spin Retry Count:        {fields['spin_retry_count']}",
        f"    Load Cycle Count:        {fields['load_cycle_count']}",
        f"    Power-Off Retract Count: {fields['power_off_retract_count']}",
        f"    Helium Level:            {fields['helium_level']}",
    ]

    if raw_data:
        raw_json = json.dumps(raw_data, indent=2, ensure_ascii=False)
        lines.extend(["", "Raw smartctl JSON:", "```json", raw_json, "```"])

    lines.extend(["", "Triggered Alerts:", alerts_text])
    return "\n".join(lines)


def _warn_if_mismatch(provider: str, api_url: str) -> None:
    url_lower = api_url.lower()

    if provider == "openai":
        suspicious = "anthropic" in url_lower or api_url.rstrip("/").endswith(
            "/messages"
        )
    else:
        suspicious = "openai" in url_lower or api_url.rstrip("/").endswith(
            "/chat/completions"
        )

    if suspicious:
        logging.warning(
            "LLM provider is '%s' but api_url does not appear to match (%s) "
            "— ensure this is intentional",
            provider,
            api_url,
        )


def call_llm(
    fields: SmartInfo,
    alerts_text: str,
    config: LLMConfig,
    raw_data: dict[str, Any] | None = None,
) -> str | None:
    """Call the configured LLM provider's API.

    Returns the LLM's analysis text, or ``None`` on any failure.
    """
    if config.provider == "anthropic":
        return _call_anthropic(fields, alerts_text, config, raw_data=raw_data)
    return _call_openai(fields, alerts_text, config, raw_data=raw_data)


def _call_openai(
    fields: SmartInfo,
    alerts_text: str,
    config: LLMConfig,
    raw_data: dict[str, Any] | None = None,
) -> str | None:
    import httpx2

    _warn_if_mismatch("openai", config.api_url)

    user_prompt = _build_prompt(fields, alerts_text, raw_data=raw_data)

    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": config.system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    try:
        response = httpx2.post(
            config.api_url, headers=headers, json=body, timeout=config.timeout
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except httpx2.HTTPStatusError as exc:
        logging.error(
            "LLM API returned HTTP %d: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx2.RequestError as exc:
        logging.error("LLM API request failed: %s", exc)
    except (KeyError, IndexError, TypeError) as exc:
        logging.error("Unexpected LLM API response format: %s", exc)
    except Exception:
        logging.exception("Unexpected error during LLM call")

    return None


def _extract_anthropic_text(data: dict[str, Any]) -> str:
    """Extract the first text content block from an Anthropic-style response.

    Tries ``text`` then ``content`` key inside each content block.
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


def _call_anthropic(
    fields: SmartInfo,
    alerts_text: str,
    config: LLMConfig,
    raw_data: dict[str, Any] | None = None,
) -> str | None:
    import httpx2

    _warn_if_mismatch("anthropic", config.api_url)

    user_prompt = _build_prompt(fields, alerts_text, raw_data=raw_data)

    body = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
        "system": config.system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    if config.api_key:
        headers["x-api-key"] = config.api_key

    try:
        response = httpx2.post(
            config.api_url, headers=headers, json=body, timeout=config.timeout
        )
        response.raise_for_status()
        data = response.json()
        return _extract_anthropic_text(data)
    except httpx2.HTTPStatusError as exc:
        logging.error(
            "LLM API returned HTTP %d: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
    except httpx2.RequestError as exc:
        logging.error("LLM API request failed: %s", exc)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        logging.error("Unexpected LLM API response format: %s", exc)
    except Exception:
        logging.exception("Unexpected error during LLM call")

    return None
