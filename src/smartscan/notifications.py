"""Notification channels: Telegram Bot, DingTalk Bot, Feishu Bot."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import socket
import time
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

import httpx2

from .models import SmartInfo
from .thresholds import Alert


def _build_report_text(
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


class BaseNotifier(ABC):
    """Abstract base for notification channel senders."""

    def __init__(self, config: Any) -> None:
        self._config = config

    @abstractmethod
    def send(self, text: str) -> bool:
        """Send a notification message. Returns ``True`` on success."""
        ...

    @staticmethod
    def _post_json(url: str, body: dict[str, Any], timeout: int = 15) -> bool:
        try:
            resp = httpx2.post(url, json=body, timeout=timeout)
            resp.raise_for_status()
            return True
        except httpx2.HTTPStatusError as exc:
            logging.error(
                "Notify HTTP %d: %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
        except httpx2.RequestError as exc:
            logging.error("Notify request failed: %s", exc)
        except Exception:
            logging.exception("Unexpected error during notification")
        return False


class TelegramNotifier(BaseNotifier):
    """Send notifications via Telegram Bot API."""

    def send(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self._config.bot_token}/sendMessage"
        body: dict[str, Any] = {"chat_id": self._config.chat_id, "text": text}
        return self._post_json(url, body)


class DingTalkNotifier(BaseNotifier):
    """Send notifications via DingTalk custom bot webhook."""

    def send(self, text: str) -> bool:
        url = self._config.webhook_url
        if self._config.secret:
            ts, sign = self._sign()
            url = f"{url}&timestamp={ts}&sign={sign}"
        body: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {"title": "smartscan report", "text": text},
        }
        return self._post_json(url, body)

    def _sign(self) -> tuple[str, str]:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self._config.secret}"
        sig = hmac.new(
            self._config.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return timestamp, urllib.parse.quote_plus(base64.b64encode(sig))


class FeishuNotifier(BaseNotifier):
    """Send notifications via Feishu custom bot webhook."""

    def send(self, text: str) -> bool:
        body: dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": text},
        }
        if self._config.secret:
            ts, sign = self._sign()
            body["timestamp"] = ts
            body["sign"] = sign
        return self._post_json(self._config.webhook_url, body)

    def _sign(self) -> tuple[str, str]:
        timestamp = str(int(time.time()))
        string_to_sign = f"{timestamp}\n{self._config.secret}"
        sig = hmac.new(
            string_to_sign.encode("utf-8"),
            self._config.secret.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return timestamp, base64.b64encode(sig).decode("utf-8")


def _get_notifiers(notify_config: Any) -> list[BaseNotifier]:
    notifiers: list[BaseNotifier] = []
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
    text = _build_report_text(hostname, disk_results, batch_llm_analysis)
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
