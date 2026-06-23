"""Generic notification channel senders — reusable across projects."""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any

import httpx2


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
