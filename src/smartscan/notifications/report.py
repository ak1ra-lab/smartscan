"""SMART-specific notification report building and dispatch."""

from __future__ import annotations

import logging
import socket
from typing import Any

from ..models import SmartInfo
from ..thresholds import Alert
from .channels import DingTalkNotifier, FeishuNotifier, TelegramNotifier


def build_report_text(
    hostname: str,
    disk_results: list[
        tuple[str, str, SmartInfo, list[Alert], dict[str, Any] | None, int, str | None]
    ],
    batch_llm_analysis: str | None = None,
) -> str:
    total = len(disk_results)
    alert_disks = [
        (name, path, fields, alerts)
        for name, path, fields, alerts, *_ in disk_results
        if alerts
    ]

    lines = [f"smartscan report — {hostname}", ""]
    lines.append(f"Disks checked: {total}")
    lines.append(f"Disks with alerts: {len(alert_disks)}")

    if alert_disks:
        lines.append("")
        lines.append("Alerts:")
        for name, path, fields, alerts in alert_disks:
            model = fields.get("model_name", "N/A")
            lines.append(f"  - {name} ({model}):")
            for a in alerts:
                lines.append(f"      [{a.level}] {a.message}")

    per_disk_llm: dict[str, str] = {}
    for entry in disk_results:
        llm_text = entry[6]
        if llm_text:
            per_disk_llm[entry[0]] = llm_text
    if per_disk_llm:
        lines.append("")
        lines.append("Per-disk LLM Analysis:")
        for name, text in per_disk_llm.items():
            lines.append(f"  {name}:")
            for line in text.strip().split("\n"):
                lines.append(f"    {line}")

    if batch_llm_analysis:
        lines.append("")
        lines.append("Batch LLM Summary:")
        for line in batch_llm_analysis.strip().split("\n"):
            lines.append(f"  {line}")

    return "\n".join(lines)


def _get_notifiers(
    notify_config: Any,
) -> list[TelegramNotifier | DingTalkNotifier | FeishuNotifier]:
    notifiers = []
    if notify_config.telegram.enabled and notify_config.telegram.bot_token:
        logging.debug("Telegram notifier enabled")
        notifiers.append(TelegramNotifier(notify_config.telegram))
    if notify_config.dingtalk.enabled and notify_config.dingtalk.webhook_url:
        logging.debug("DingTalk notifier enabled")
        notifiers.append(DingTalkNotifier(notify_config.dingtalk))
    if notify_config.feishu.enabled and notify_config.feishu.webhook_url:
        logging.debug("Feishu notifier enabled")
        notifiers.append(FeishuNotifier(notify_config.feishu))
    if not notifiers:
        logging.info("No notification channels configured, skipping.")
    return notifiers


def send_notifications(
    notify_config: Any,
    disk_results: list[
        tuple[str, str, SmartInfo, list[Alert], dict[str, Any] | None, int, str | None]
    ],
    batch_llm_analysis: str | None = None,
) -> None:
    hostname = socket.gethostname()
    text = build_report_text(hostname, disk_results, batch_llm_analysis)
    logging.debug("Report text length: %d chars", len(text))

    notifiers = _get_notifiers(notify_config)
    logging.debug("%d notification channel(s) ready", len(notifiers))

    for notifier in notifiers:
        name = type(notifier).__name__
        logging.info("Sending %s notification ...", name)
        try:
            notifier.send(text)
        except Exception:
            logging.exception("Notification failed for %s", name)
