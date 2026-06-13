from __future__ import annotations

from unittest.mock import patch

import pytest
from conftest import make_fields

from smartscan.database import init_db, parse_date, query_smart_info, save_to_db
from smartscan.exceptions import InvalidDateError
from smartscan.models import ThresholdRules
from smartscan.smartctl import extract_fields, find_in_table, safe_get
from smartscan.thresholds import check_thresholds


class TestSafeGet:
    def test_simple_key(self) -> None:
        assert safe_get({"foo": "bar"}, "foo") == "bar"

    def test_nested_keys(self) -> None:
        assert safe_get({"a": {"b": {"c": 42}}}, "a", "b", "c") == 42

    def test_missing_key_defaults(self) -> None:
        assert safe_get({}, "missing") == "N/A"

    def test_none_value_defaults(self) -> None:
        assert safe_get({"x": None}, "x") == "N/A"

    def test_empty_string_defaults(self) -> None:
        assert safe_get({"x": ""}, "x") == "N/A"

    def test_null_string_defaults(self) -> None:
        assert safe_get({"x": "null"}, "x") == "N/A"

    def test_custom_default(self) -> None:
        assert safe_get({}, "missing", default=0) == 0

    def test_non_dict_intermediate(self) -> None:
        assert safe_get({"a": "not-a-dict"}, "a", "b") == "N/A"


class TestFindInTable:
    def test_find_value(self) -> None:
        data = {
            "ata_smart_attributes": {
                "table": [
                    {"name": "Temperature_Celsius", "raw": {"string": "35"}},
                    {"name": "Reallocated_Sector_Ct", "raw": {"string": "0"}},
                    {"name": "Current_Pending_Sector", "raw": {"string": "0"}},
                ]
            }
        }
        result = find_in_table(
            data,
            ("ata_smart_attributes", "table"),
            "name",
            "Reallocated_Sector_Ct",
            ("raw", "string"),
        )
        assert result == "0"

    def test_find_current_pending(self) -> None:
        data = {
            "ata_smart_attributes": {
                "table": [
                    {"name": "Current_Pending_Sector", "raw": {"string": "3"}},
                ]
            }
        }
        result = find_in_table(
            data,
            ("ata_smart_attributes", "table"),
            "name",
            "Current_Pending_Sector",
            ("raw", "string"),
        )
        assert result == "3"

    def test_not_found_returns_default(self) -> None:
        data = {"ata_smart_attributes": {"table": []}}
        result = find_in_table(
            data,
            ("ata_smart_attributes", "table"),
            "name",
            "Reallocated_Sector_Ct",
            ("raw", "string"),
        )
        assert result == "0"

    def test_missing_table_key(self) -> None:
        data = {}
        result = find_in_table(
            data,
            ("nonexistent", "table"),
            "name",
            "x",
            ("raw", "string"),
        )
        assert result == "0"


class TestExtractFields:
    def test_extract_basic_fields(self) -> None:
        data = {
            "model_family": "Seagate BarraCuda",
            "model_name": "ST2000DM008-2FR102",
            "serial_number": "ABC123",
            "firmware_version": "1.0",
            "user_capacity": {"bytes": 2000398934016},
            "rotation_rate": 7200,
            "interface_speed": {"current": {"string": "6.0 Gb/s"}},
            "power_on_time": {"hours": 12345},
            "power_cycle_count": 500,
            "smart_status": {"passed": True},
            "temperature": {"current": 35},
            "ata_smart_error_log": {"summary": {"count": 0}},
            "ata_smart_data": {
                "self_test": {"status": {"string": "Completed without error"}}
            },
        }
        fields = extract_fields(data)
        assert fields["model_family"] == "Seagate BarraCuda"
        assert fields["model_name"] == "ST2000DM008-2FR102"
        assert fields["serial_number"] == "ABC123"
        assert fields["firmware_version"] == "1.0"
        assert fields["user_capacity_bytes"] == 2000398934016
        assert fields["user_capacity_gib"] == pytest.approx(1863.01, abs=0.01)
        assert fields["rotation_rate_display"] == "7200 rpm"
        assert fields["interface_speed"] == "6.0 Gb/s"
        assert fields["power_on_time"] == "12345"
        assert fields["power_cycle_count"] == "500"
        assert fields["smart_status"] == "PASSED"
        assert fields["temperature"] == "35"
        assert fields["ata_smart_error_log"] == "0"
        assert fields["self_test_status"] == "Completed without error"

    def test_smart_status_failed(self) -> None:
        data = {
            "model_family": "Failing Drive",
            "model_name": "WD10EZEX",
            "smart_status": {"passed": False},
        }
        fields = extract_fields(data)
        assert fields["smart_status"] == "FAILED"

    def test_ssd_rotation_rate_display(self) -> None:
        data = {
            "model_family": "Samsung SSD",
            "model_name": "Samsung SSD 860 EVO",
            "user_capacity": {"bytes": 500107862016},
            "rotation_rate": 0,
            "interface_speed": {"current": {"string": "6.0 Gb/s"}},
            "power_on_time": {"hours": 1000},
            "power_cycle_count": 100,
            "smart_status": {"passed": True},
            "temperature": {"current": 30},
            "ata_smart_error_log": {"summary": {"count": 0}},
            "ata_smart_data": {"self_test": {"status": {"string": "Completed"}}},
        }
        fields = extract_fields(data)
        assert fields["rotation_rate"] == "0"
        assert fields["rotation_rate_display"] == "SSD (no rotation)"

    def test_reallocated_sectors_found(self) -> None:
        data = {
            "model_family": "Old Drive",
            "model_name": "WDC WD10EZEX",
            "user_capacity": {"bytes": 1000204886016},
            "rotation_rate": 7200,
            "interface_speed": {"current": {"string": "6.0 Gb/s"}},
            "power_on_time": {"hours": 50000},
            "power_cycle_count": 2000,
            "smart_status": {"passed": True},
            "temperature": {"current": 40},
            "ata_smart_attributes": {
                "table": [
                    {"name": "Reallocated_Sector_Ct", "raw": {"string": "5"}},
                ]
            },
            "ata_smart_error_log": {"summary": {"count": 3}},
            "ata_smart_data": {
                "self_test": {"status": {"string": "Self-test routine in progress"}}
            },
        }
        fields = extract_fields(data)
        assert fields["reallocated_sector_ct"] == "5"

    def test_extract_all_new_attributes(self) -> None:
        data = {
            "model_family": "Full Drive",
            "model_name": "Full Model",
            "user_capacity": {"bytes": 1000000000000},
            "rotation_rate": 7200,
            "interface_speed": {"current": {"string": "6.0 Gb/s"}},
            "power_on_time": {"hours": 10000},
            "power_cycle_count": 50,
            "smart_status": {"passed": True},
            "temperature": {"current": 30},
            "ata_smart_attributes": {
                "table": [
                    {"name": "Reallocated_Sector_Ct", "raw": {"string": "0"}},
                    {"name": "Current_Pending_Sector", "raw": {"string": "0"}},
                    {"name": "Offline_Uncorrectable", "raw": {"string": "0"}},
                    {"name": "Reallocated_Event_Count", "raw": {"string": "1"}},
                    {"name": "UDMA_CRC_Error_Count", "raw": {"string": "2"}},
                    {"name": "Raw_Read_Error_Rate", "raw": {"string": "3"}},
                    {"name": "Spin_Retry_Count", "raw": {"string": "0"}},
                    {"name": "Power-Off_Retract_Count", "raw": {"string": "10"}},
                    {"name": "Load_Cycle_Count", "raw": {"string": "500"}},
                    {"name": "Helium_Level", "raw": {"string": "100"}},
                ]
            },
            "ata_smart_error_log": {"summary": {"count": 0}},
            "ata_smart_data": {
                "self_test": {"status": {"string": "Completed without error"}}
            },
        }
        fields = extract_fields(data)
        assert fields["current_pending_sector"] == "0"
        assert fields["offline_uncorrectable"] == "0"
        assert fields["reallocated_event_count"] == "1"
        assert fields["udma_crc_error_count"] == "2"
        assert fields["raw_read_error_rate"] == "3"
        assert fields["spin_retry_count"] == "0"
        assert fields["power_off_retract_count"] == "10"
        assert fields["load_cycle_count"] == "500"
        assert fields["helium_level"] == "100"

    def test_missing_optional_fields(self) -> None:
        data: dict = {}
        fields = extract_fields(data)
        assert fields["model_family"] == "N/A"
        assert fields["model_name"] == "N/A"
        assert fields["serial_number"] == "N/A"
        assert fields["firmware_version"] == "N/A"
        assert fields["user_capacity_bytes"] == 0
        assert fields["user_capacity_gib"] is None
        assert fields["smart_status"] == "FAILED"
        assert fields["reallocated_sector_ct"] == "0"
        assert fields["current_pending_sector"] == "0"
        assert fields["offline_uncorrectable"] == "0"
        assert fields["ata_smart_error_log"] == "0"
        assert fields["self_test_status"] == "N/A"


class TestThresholds:
    def test_no_alerts_on_healthy_drive(self) -> None:
        fields = make_fields(
            smart_status="PASSED",
            temperature="35",
            reallocated_sector_ct="0",
            current_pending_sector="0",
            offline_uncorrectable="0",
        )
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert alerts == []

    def test_smart_status_failed_critical(self) -> None:
        fields = make_fields(smart_status="FAILED")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert len(alerts) == 1
        assert alerts[0].field == "smart_status"
        assert alerts[0].level == "critical"

    def test_temperature_warning(self) -> None:
        fields = make_fields(temperature="55")
        rules = ThresholdRules(temperature_celsius=50)
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "temperature" and a.level == "warning" for a in alerts)

    def test_temperature_ok_below_threshold(self) -> None:
        fields = make_fields(temperature="49")
        rules = ThresholdRules(temperature_celsius=50)
        alerts = check_thresholds(fields, rules)
        assert not any(a.field == "temperature" for a in alerts)

    def test_reallocated_sector_warning(self) -> None:
        fields = make_fields(reallocated_sector_ct="5")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(
            a.field == "reallocated_sector_ct" and a.level == "warning" for a in alerts
        )

    def test_reallocated_sector_critical_above_10(self) -> None:
        fields = make_fields(reallocated_sector_ct="21")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        realloc_alerts = [a for a in alerts if a.field == "reallocated_sector_ct"]
        assert len(realloc_alerts) == 1
        assert realloc_alerts[0].level == "critical"

    def test_pending_sector_critical(self) -> None:
        fields = make_fields(current_pending_sector="3")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(
            a.field == "current_pending_sector" and a.level == "critical"
            for a in alerts
        )

    def test_offline_uncorrectable_critical(self) -> None:
        fields = make_fields(offline_uncorrectable="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(
            a.field == "offline_uncorrectable" and a.level == "critical" for a in alerts
        )

    def test_self_test_failure_warning(self) -> None:
        fields = make_fields(self_test_status="Failed in segment 3")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(
            a.field == "self_test_status" and a.level == "warning" for a in alerts
        )

    def test_self_test_healthy(self) -> None:
        fields = make_fields(self_test_status="Completed without error")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert not any(a.field == "self_test_status" for a in alerts)

    def test_multiple_alerts(self) -> None:
        fields = make_fields(
            smart_status="FAILED",
            temperature="60",
            reallocated_sector_ct="15",
            current_pending_sector="2",
        )
        rules = ThresholdRules(temperature_celsius=50)
        alerts = check_thresholds(fields, rules)
        assert len(alerts) >= 4

    def test_disabled_thresholds(self) -> None:
        fields = make_fields(
            smart_status="FAILED",
            temperature="60",
        )
        rules = ThresholdRules(enabled=False)
        alerts = check_thresholds(fields, rules)
        assert alerts == []

    def test_custom_threshold_values(self) -> None:
        fields = make_fields(temperature="55")
        rules = ThresholdRules(temperature_celsius=60)
        alerts = check_thresholds(fields, rules)
        assert not any(a.field == "temperature" for a in alerts)

    def test_load_cycle_warning(self) -> None:
        fields = make_fields(load_cycle_count="700000")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "load_cycle_count" for a in alerts)

    def test_udma_crc_warning(self) -> None:
        fields = make_fields(udma_crc_error_count="5")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "udma_crc_error_count" for a in alerts)


class TestParseDate:
    def test_valid_date(self) -> None:
        dt = parse_date("2024-01-15")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_invalid_date_raises(self) -> None:
        with pytest.raises(InvalidDateError):
            parse_date("not-a-date")

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(InvalidDateError):
            parse_date("15-01-2024")


class TestDatabase:
    def test_init_db_creates_tables(self) -> None:
        conn = init_db(":memory:")
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [row["name"] for row in tables]
        assert "smart_info" in names
        conn.close()

    def test_init_db_runs_migrations(self) -> None:
        conn = init_db(":memory:")
        columns = conn.execute("PRAGMA table_info(smart_info)").fetchall()
        col_names = [row["name"] for row in columns]
        assert "smart_status" in col_names
        assert "current_pending_sector" in col_names
        assert "llm_analysis" in col_names
        conn.close()

    def test_save_and_query(self) -> None:
        conn = init_db(":memory:")

        fields = make_fields(
            model_family="Test Family",
            model_name="Test Model",
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
        save_to_db(conn, "sda", "/dev/sda", fields, {"raw": "data"})

        rows = query_smart_info(conn, None, None, None)
        assert len(rows) == 1
        assert rows[0]["disk_name"] == "sda"
        assert rows[0]["model_family"] == "Test Family"
        assert rows[0]["reallocated_sector_ct"] == "0"

        conn.close()

    def test_save_with_llm_analysis(self) -> None:
        conn = init_db(":memory:")
        fields = make_fields(reallocated_sector_ct="21")
        save_to_db(
            conn,
            "sda",
            "/dev/sda",
            fields,
            {},
            llm_analysis="Drive has 21 reallocated sectors — replace soon.",
        )
        rows = query_smart_info(conn, None, None, None)
        assert (
            rows[0]["llm_analysis"]
            == "Drive has 21 reallocated sectors — replace soon."
        )
        conn.close()

    def test_query_with_pattern(self) -> None:
        conn = init_db(":memory:")

        fields = make_fields()
        save_to_db(conn, "ata-WDC", "/dev/sda", fields, {})
        save_to_db(conn, "ata-Samsung", "/dev/sdb", fields, {})

        rows = query_smart_info(conn, "WDC", None, None)
        assert len(rows) == 1
        assert rows[0]["disk_name"] == "ata-WDC"

        conn.close()


class TestBuildDeviceTree:
    def test_exclude_patterns_filters_devices(self) -> None:
        from smartscan.smartctl import build_device_tree

        class FakeEntry:
            def __init__(self, name: str, target: str, is_symlink: bool = True) -> None:
                self._name = name
                self._target = target
                self._is_symlink = is_symlink

            def is_symlink(self) -> bool:
                return self._is_symlink  # type: ignore[attr-defined]

            @property
            def name(self) -> str:
                return self._name

            def resolve(self) -> "FakePath":
                return FakePath(self._target)

            def __lt__(self, other: "FakeEntry") -> bool:
                return self._name < other._name

        class FakePath:
            def __init__(self, p: str) -> None:
                self._p = p

            def __truediv__(self, other: str) -> "FakePath":
                return FakePath(f"{self._p}/{other}")

            def is_dir(self) -> bool:
                return self._p in ("/dev/disk", "/dev/disk/by-diskseq")

            def iterdir(self) -> list:
                return entries

            def __str__(self) -> str:
                return self._p

        entries = [
            FakeEntry("ata-Samsung_SSD", "/dev/sda"),
            FakeEntry("1", "/dev/loop0"),
            FakeEntry("zd16", "/dev/zd16"),
        ]

        def _mock_is_whole_disk(dev_path: str) -> bool:
            return True

        def _mock_get_disk_info(dev_path: str) -> tuple:
            return "TestModel", "1.0 TiB", 1099511627776

        with (
            patch("smartscan.smartctl.Path", FakePath),
            patch(
                "smartscan.smartctl._is_whole_disk",
                side_effect=_mock_is_whole_disk,
            ),
            patch(
                "smartscan.smartctl._get_disk_info",
                side_effect=_mock_get_disk_info,
            ),
        ):
            result = build_device_tree(
                sources=("by-diskseq",),
                exclude_patterns=["^/dev/(loop|zd)\\d+"],
            )

        assert len(result) == 1
        assert result[0]["device"] == "/dev/sda"
