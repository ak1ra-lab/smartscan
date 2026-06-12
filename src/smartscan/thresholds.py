"""Threshold checking against SMART fields with pre-defined industry best practices."""

from __future__ import annotations

from dataclasses import dataclass

from .models import SmartInfo, ThresholdRules


@dataclass
class Alert:
    field: str
    level: str  # "critical" | "warning"
    message: str


def _int_val(value: str) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _self_test_healthy(status: str) -> bool:
    if status in ("N/A", ""):
        return True
    lowered = status.lower()
    return "pass" in lowered or "completed" in lowered


def _build_alert(field: str, level: str, value: str, threshold: int) -> Alert:
    return Alert(
        field=field,
        level=level,
        message=f"{field}: {value} (threshold: {threshold})",
    )


def check_thresholds(fields: SmartInfo, rules: ThresholdRules) -> list[Alert]:
    alerts: list[Alert] = []

    if not rules.enabled:
        return alerts

    smart_status = fields["smart_status"]
    if smart_status != "PASSED":
        alerts.append(
            Alert(
                field="smart_status",
                level="critical",
                message="SMART overall health self-assessment: FAILED",
            )
        )

    self_test = fields["self_test_status"]
    if not _self_test_healthy(self_test):
        alerts.append(
            Alert(
                field="self_test_status",
                level="warning",
                message=f"Self-test status: {self_test}",
            )
        )

    field_values: dict[str, int | None] = {
        "temperature": _int_val(fields["temperature"]),
        "reallocated_sector_ct": _int_val(fields["reallocated_sector_ct"]),
        "current_pending_sector": _int_val(fields["current_pending_sector"]),
        "offline_uncorrectable": _int_val(fields["offline_uncorrectable"]),
        "reallocated_event_count": _int_val(fields["reallocated_event_count"]),
        "ata_smart_error_log": _int_val(fields["ata_smart_error_log"]),
        "udma_crc_error_count": _int_val(fields["udma_crc_error_count"]),
        "spin_retry_count": _int_val(fields["spin_retry_count"]),
        "load_cycle_count": _int_val(fields["load_cycle_count"]),
    }

    thresholds: dict[str, int] = {
        "temperature": rules.temperature_celsius,
        "reallocated_sector_ct": rules.reallocated_sector_ct,
        "current_pending_sector": rules.current_pending_sector,
        "offline_uncorrectable": rules.offline_uncorrectable,
        "reallocated_event_count": rules.reallocated_event_count,
        "ata_smart_error_log": rules.ata_smart_error_log_count,
        "udma_crc_error_count": rules.udma_crc_error_count,
        "spin_retry_count": rules.spin_retry_count,
        "load_cycle_count": rules.load_cycle_count,
    }

    for field_name, threshold in thresholds.items():
        value = field_values.get(field_name)
        if value is not None and value > threshold:
            level = (
                "critical"
                if field_name in ("current_pending_sector", "offline_uncorrectable")
                else "warning"
            )
            alerts.append(_build_alert(field_name, level, str(value), threshold))

    realloc_val = field_values.get("reallocated_sector_ct")
    if realloc_val is not None and realloc_val > 10:
        for a in alerts:
            if a.field == "reallocated_sector_ct":
                a.level = "critical"
                a.message = (
                    f"reallocated_sector_ct: {realloc_val} "
                    f"(threshold: {rules.reallocated_sector_ct}, >10=critical)"
                )

    return alerts
