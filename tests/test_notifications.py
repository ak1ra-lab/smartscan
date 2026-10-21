"""Tests for notification report building and channel signing."""

from __future__ import annotations

from unittest.mock import patch

from conftest import make_fields

from smartscan.models import FeishuConfig
from smartscan.notifications.channels import FeishuNotifier
from smartscan.notifications.report import build_report_text
from smartscan.results import DiskEntry
from smartscan.thresholds import Alert


def test_feishu_signature_matches_documented_algorithm() -> None:
    notifier = FeishuNotifier(FeishuConfig(secret="test-secret"))

    with patch("smartscan.notifications.channels.time.time", return_value=1700000000):
        timestamp, sign = notifier._sign()

    assert timestamp == "1700000000"
    assert sign == "mbm4Y4oluIPQ00qlBIhX8vAZ0EKv3nw0LuTb91jPL84="


def test_report_includes_alerts_and_llm_analysis() -> None:
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
        returncode=0,
        llm_analysis="Drive is warm.",
    )

    text = build_report_text("test-host", [entry], batch_llm_analysis="Summary")

    assert "sda (Test Model)" in text
    assert "[warning] temperature: 55 (threshold: 50)" in text
    assert "Per-disk LLM Analysis:" in text
    assert "Drive is warm." in text
    assert "Batch LLM Summary:" in text
