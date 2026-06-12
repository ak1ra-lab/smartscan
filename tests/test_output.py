from __future__ import annotations

import io
import json
import sqlite3
import sys

from smartscan.output import print_json_output, row_to_fields


def _make_row(data: dict) -> sqlite3.Row:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute(
            "CREATE TABLE t (model_family, model_name, serial_number, firmware_version, "
            "user_capacity_bytes, user_capacity_gib, rotation_rate, interface_speed, "
            "power_on_time_hours, power_cycle_count, smart_status, temperature_celsius, "
            "reallocated_sector_ct, current_pending_sector, offline_uncorrectable, "
            "reallocated_event_count, ata_smart_error_log_count, self_test_status, "
            "udma_crc_error_count, raw_read_error_rate, spin_retry_count, "
            "power_off_retract_count, load_cycle_count, helium_level)"
        )
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        conn.execute(
            f"INSERT INTO t ({cols}) VALUES ({placeholders})", list(data.values())
        )
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM t").fetchone()
    finally:
        conn.close()


class TestRowToFields:
    def test_basic_conversion(self) -> None:
        row = _make_row(
            {
                "model_family": "Seagate",
                "model_name": "ST2000",
                "serial_number": "ABC123",
                "firmware_version": "1.0",
                "user_capacity_bytes": 2000398934016,
                "user_capacity_gib": 1863.01,
                "rotation_rate": "7200",
                "interface_speed": "6.0 Gb/s",
                "power_on_time_hours": "12345",
                "power_cycle_count": "500",
                "smart_status": "PASSED",
                "temperature_celsius": "35",
                "reallocated_sector_ct": "0",
                "current_pending_sector": "0",
                "offline_uncorrectable": "0",
                "reallocated_event_count": "0",
                "ata_smart_error_log_count": "0",
                "self_test_status": "OK",
                "udma_crc_error_count": "0",
                "raw_read_error_rate": "0",
                "spin_retry_count": "0",
                "power_off_retract_count": "0",
                "load_cycle_count": "0",
                "helium_level": "0",
            }
        )
        info = row_to_fields(row)
        assert info["model_family"] == "Seagate"
        assert info["user_capacity_gib"] == 1863.01
        assert info["rotation_rate_display"] == "7200 rpm"
        assert info["power_on_time"] == "12345"
        assert info["temperature"] == "35"
        assert info["smart_status"] == "PASSED"

    def test_ssd_rotation_display(self) -> None:
        row = _make_row(
            {
                "model_family": "Samsung",
                "model_name": "860 EVO",
                "serial_number": "",
                "firmware_version": "",
                "user_capacity_bytes": 500107862016,
                "user_capacity_gib": 465.76,
                "rotation_rate": "0",
                "interface_speed": "6.0 Gb/s",
                "power_on_time_hours": "1000",
                "power_cycle_count": "100",
                "smart_status": "PASSED",
                "temperature_celsius": "30",
                "reallocated_sector_ct": "0",
                "current_pending_sector": "0",
                "offline_uncorrectable": "0",
                "reallocated_event_count": "0",
                "ata_smart_error_log_count": "0",
                "self_test_status": "OK",
                "udma_crc_error_count": "0",
                "raw_read_error_rate": "0",
                "spin_retry_count": "0",
                "power_off_retract_count": "0",
                "load_cycle_count": "0",
                "helium_level": "0",
            }
        )
        info = row_to_fields(row)
        assert info["rotation_rate"] == "0"
        assert info["rotation_rate_display"] == "SSD (no rotation)"

    def test_new_fields_preserved(self) -> None:
        row = _make_row(
            {
                "model_family": "WD",
                "model_name": "HC550",
                "serial_number": "2BK5EV4N",
                "firmware_version": "PCGNW232",
                "user_capacity_bytes": 16000900661248,
                "user_capacity_gib": 14901.95,
                "rotation_rate": "7200",
                "interface_speed": "6.0 Gb/s",
                "power_on_time_hours": "24187",
                "power_cycle_count": "31",
                "smart_status": "PASSED",
                "temperature_celsius": "33",
                "reallocated_sector_ct": "21",
                "current_pending_sector": "0",
                "offline_uncorrectable": "0",
                "reallocated_event_count": "21",
                "ata_smart_error_log_count": "0",
                "self_test_status": "Completed without error",
                "udma_crc_error_count": "0",
                "raw_read_error_rate": "0",
                "spin_retry_count": "0",
                "power_off_retract_count": "1127",
                "load_cycle_count": "1127",
                "helium_level": "100",
            }
        )
        info = row_to_fields(row)
        assert info["current_pending_sector"] == "0"
        assert info["offline_uncorrectable"] == "0"
        assert info["reallocated_event_count"] == "21"
        assert info["power_off_retract_count"] == "1127"
        assert info["helium_level"] == "100"


class TestPrintJsonOutput:
    def test_output_format(self) -> None:
        from conftest import make_fields

        fields = make_fields(
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
        assert record["smart_status"] == "PASSED"

    def test_output_without_timestamp(self) -> None:
        from conftest import make_fields

        fields = make_fields()
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

    def test_output_with_llm_analysis(self) -> None:
        from conftest import make_fields

        fields = make_fields()
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            print_json_output(
                "sdc",
                "/dev/sdc",
                fields,
                llm_analysis="Drive appears healthy.",
            )
        finally:
            sys.stdout = old_stdout

        output = buf.getvalue()
        record = json.loads(output)
        assert record["llm_analysis"] == "Drive appears healthy."
