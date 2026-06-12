from __future__ import annotations

import io
import json
import sqlite3
import sys

from smartscan.models import SmartInfo
from smartscan.output import print_json_output, row_to_fields


def _make_row(data: dict) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE t (model_family, model_name, user_capacity_bytes, "
        "user_capacity_gib, rotation_rate, interface_speed, power_on_time_hours, "
        "power_cycle_count, temperature_celsius, reallocated_sector_ct, "
        "ata_smart_error_log_count, self_test_status)"
    )
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" * len(data))
    conn.execute(f"INSERT INTO t ({cols}) VALUES ({placeholders})", list(data.values()))
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM t").fetchone()


class TestRowToFields:
    def test_basic_conversion(self) -> None:
        row = _make_row(
            {
                "model_family": "Seagate",
                "model_name": "ST2000",
                "user_capacity_bytes": 2000398934016,
                "user_capacity_gib": 1863.01,
                "rotation_rate": "7200",
                "interface_speed": "6.0 Gb/s",
                "power_on_time_hours": "12345",
                "power_cycle_count": "500",
                "temperature_celsius": "35",
                "reallocated_sector_ct": "0",
                "ata_smart_error_log_count": "0",
                "self_test_status": "OK",
            }
        )
        info = row_to_fields(row)
        assert info["model_family"] == "Seagate"
        assert info["user_capacity_gib"] == 1863.01
        assert info["rotation_rate_display"] == "7200 rpm"
        assert info["power_on_time"] == "12345"
        assert info["temperature"] == "35"

    def test_ssd_rotation_display(self) -> None:
        row = _make_row(
            {
                "model_family": "Samsung",
                "model_name": "860 EVO",
                "user_capacity_bytes": 500107862016,
                "user_capacity_gib": 465.76,
                "rotation_rate": "0",
                "interface_speed": "6.0 Gb/s",
                "power_on_time_hours": "1000",
                "power_cycle_count": "100",
                "temperature_celsius": "30",
                "reallocated_sector_ct": "0",
                "ata_smart_error_log_count": "0",
                "self_test_status": "OK",
            }
        )
        info = row_to_fields(row)
        assert info["rotation_rate"] == "0"
        assert info["rotation_rate_display"] == "SSD (no rotation)"


class TestPrintJsonOutput:
    def test_output_format(self) -> None:
        fields = SmartInfo(
            model_family="Test",
            model_name="Model",
            user_capacity_bytes=1000,
            user_capacity_gib=0.0,
            rotation_rate="7200",
            rotation_rate_display="7200 rpm",
            interface_speed="6.0 Gb/s",
            power_on_time="100",
            power_cycle_count="10",
            temperature="35",
            reallocated_sector_ct="0",
            ata_smart_error_log="0",
            self_test_status="OK",
        )
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_json_output(
                "sda",
                "/dev/sda",
                fields,
                {"raw": "data"},
                timestamp="2024-01-01T00:00:00Z",
            )
        finally:
            sys.stdout = old_stdout

        output = buf.getvalue()
        record = json.loads(output)
        assert record["disk_name"] == "sda"
        assert record["disk_path"] == "/dev/sda"
        assert record["timestamp"] == "2024-01-01T00:00:00Z"
        assert record["model_family"] == "Test"

    def test_output_without_timestamp(self) -> None:
        fields = SmartInfo(
            model_family="",
            model_name="",
            user_capacity_bytes=0,
            user_capacity_gib=None,
            rotation_rate="",
            rotation_rate_display="",
            interface_speed="",
            power_on_time="",
            power_cycle_count="",
            temperature="",
            reallocated_sector_ct="0",
            ata_smart_error_log="",
            self_test_status="",
        )
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_json_output("sdb", "/dev/sdb", fields)
        finally:
            sys.stdout = old_stdout

        output = buf.getvalue()
        record = json.loads(output)
        assert "timestamp" not in record
        assert record["disk_name"] == "sdb"
