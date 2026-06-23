"""SMART-specific LLM prompt builders."""

from __future__ import annotations

import json
from typing import Any

from ..fields import (
    BASIC_PROMPT_FIELDS,
    CRITICAL_PROMPT_FIELDS,
    SECONDARY_PROMPT_FIELDS,
    get_field,
)
from ..models import SmartInfo
from ..smartctl import smartctl_error_lines
from .providers import lang_instruction


def _format_prompt_fields(fields: SmartInfo, indent: str = "  ") -> list[str]:
    """Render BASIC/CRITICAL/SECONDARY prompt fields with shared formatting."""
    lines: list[str] = []

    for f in BASIC_PROMPT_FIELDS:
        value = get_field(fields, f.key)
        label = f.prompt_label or f.key
        if f.key == "user_capacity_gib" and value is None:
            lines.append(f"{indent}{label}:      N/A")
        elif f.format_label:
            lines.append(f"{indent}{label}: {f.format_label.format(value=value)}")
        else:
            lines.append(f"{indent}{label}: {value}")

    lines.append("")
    lines.append(f"{indent}Critical Attributes:")
    for f in CRITICAL_PROMPT_FIELDS:
        lines.append(
            f"{indent}  {f.prompt_label or f.key}:     {get_field(fields, f.key)}"
        )

    lines.append("")
    lines.append(f"{indent}Secondary Attributes:")
    for f in SECONDARY_PROMPT_FIELDS:
        lines.append(
            f"{indent}  {f.prompt_label or f.key}:         {get_field(fields, f.key)}"
        )

    return lines


def build_prompt(
    fields: SmartInfo,
    alerts_text: str,
    raw_data: dict[str, Any] | None = None,
    returncode: int | None = None,
    lang: str | None = None,
) -> str:
    lines = ["SMART Data for Analysis:", ""]
    lines.extend(_format_prompt_fields(fields, indent="  "))

    if raw_data:
        raw_json = json.dumps(raw_data, indent=2, ensure_ascii=False)
        lines.extend(["", "Raw smartctl JSON:", "```json", raw_json, "```"])

    lines.extend(["", "Triggered Alerts:", alerts_text])

    if returncode is not None and returncode != 0:
        lines.append("")
        lines.extend(smartctl_error_lines(returncode))

    instruction = lang_instruction(lang)
    if instruction:
        lines.extend(["", instruction])

    return "\n".join(lines)


def build_batch_prompt(
    entries: list[
        tuple[str, str, SmartInfo, list[Any], dict[str, Any] | None, int, str | None]
    ],
    lang: str | None = None,
) -> str:
    lines = [
        f"SMART data from {len(entries)} disk devices is provided below.",
        "",
    ]

    for disk_name, disk_path, fields, alerts, _raw_data, rc, _llm_analysis in entries:
        model = fields.get("model_name", "N/A")
        lines.append(f"## Disk: {disk_name} ({model})")
        lines.append(f"  Path: {disk_path}")
        lines.append("")

        lines.extend(_format_prompt_fields(fields, indent="    "))

        lines.append("")
        if alerts:
            lines.append("    Alerts:")
            for a in alerts:
                lines.append(f"      - {a.message}")
        else:
            lines.append("    Alerts: (none)")

        if rc is not None and rc != 0:
            lines.append("")
            lines.append("    smartctl errors:")
            lines.extend(f"      {line}" for line in smartctl_error_lines(rc))

        lines.append("")

    instruction = lang_instruction(lang)
    if instruction:
        lines.append(instruction)

    return "\n".join(lines)


def build_trend_prompt(
    disk_name: str,
    disk_path: str,
    entries: list[tuple[str, SmartInfo]],
    lang: str | None = None,
) -> str:
    from ..fields import MONITORED_FIELDS, TIME_SERIES_FIELDS

    lines = [
        f"SMART Trend Data for Disk: {disk_name}",
        f"  Path: {disk_path}",
        "",
        f"  {len(entries)} historical records (compacted for significant changes only):",
        "",
    ]

    identity_keys = ("model_name", "model_family", "serial_number", "user_capacity_gib")
    if entries:
        first = entries[0][1]
        for key in identity_keys:
            val = first.get(key, "N/A")
            if val and str(val) != "N/A":
                lines.append(f"  {key}: {val}")
        lines.append("")

    lines.append("  Time-series of monitored health attributes:")
    lines.append(
        f"  {'Timestamp':<22}" + "  ".join(f"{k:<14}" for k in sorted(MONITORED_FIELDS))
    )
    lines.append("  " + "-" * (22 + 18 * len(MONITORED_FIELDS)))

    for ts, fields in entries:
        vals = [str(fields.get(k, "N/A")) for k in sorted(MONITORED_FIELDS)]
        lines.append(f"  {ts:<22}" + "  ".join(f"{v:<14}" for v in vals))

    lines.extend(
        [
            "",
            "Contextual counters (not used for change detection):",
        ]
    )
    for key in sorted(TIME_SERIES_FIELDS):
        all_vals = []
        for ts, fields in entries:
            all_vals.append(f"{ts}: {fields.get(key, 'N/A')}")
        lines.append(f"  {key}: " + ", ".join(all_vals[-3:]))

    lines.extend(
        [
            "",
            "Analyze the trend of the monitored health attributes over time.",
            "Identify any concerning patterns (e.g. steady increase in reallocated sectors,",
            "temperature trending upward, increasing error rates).",
            "If all metrics are stable, state that the drive health is stable.",
            "Be factual and conservative. Do not cause unnecessary alarm for normal fluctuations.",
        ]
    )

    instruction = lang_instruction(lang)
    if instruction:
        lines.append(instruction)

    return "\n".join(lines)
