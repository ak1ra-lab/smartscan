"""LLM integration: prompt construction and API calls via httpx2."""

from __future__ import annotations

import logging

from .constants import DEFAULT_SYSTEM_PROMPT
from .models import LLMConfig, SmartInfo


def _build_prompt(fields: SmartInfo, alerts_text: str) -> str:
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
        "",
        "Triggered Alerts:",
        alerts_text,
    ]
    return "\n".join(lines)


def call_llm(
    fields: SmartInfo,
    alerts_text: str,
    config: LLMConfig,
) -> str | None:
    """Call the OpenAI-compatible chat completions API.

    Returns the LLM's analysis text, or ``None`` on any failure.
    """
    import httpx2

    user_prompt = _build_prompt(fields, alerts_text)
    endpoint = config.endpoint.rstrip("/") + "/chat/completions"

    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": config.max_tokens,
        "temperature": 0.3,
    }

    try:
        response = httpx2.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=config.timeout,
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
