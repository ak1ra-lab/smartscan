from __future__ import annotations

import pytest

from smartscan.database import init_db, parse_date, query_smart_info, save_to_db
from smartscan.exceptions import InvalidDateError
from smartscan.models import SmartInfo
from smartscan.smartctl import extract_fields, find_in_table, safe_get


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
            "user_capacity": {"bytes": 2000398934016},
            "rotation_rate": 7200,
            "interface_speed": {"current": {"string": "6.0 Gb/s"}},
            "power_on_time": {"hours": 12345},
            "power_cycle_count": 500,
            "temperature": {"current": 35},
            "ata_smart_error_log": {"summary": {"count": 0}},
            "ata_smart_data": {
                "self_test": {"status": {"string": "Completed without error"}}
            },
        }
        fields = extract_fields(data)
        assert fields["model_family"] == "Seagate BarraCuda"
        assert fields["model_name"] == "ST2000DM008-2FR102"
        assert fields["user_capacity_bytes"] == 2000398934016
        assert fields["user_capacity_gib"] == pytest.approx(1863.01, abs=0.01)
        assert fields["rotation_rate_display"] == "7200 rpm"
        assert fields["interface_speed"] == "6.0 Gb/s"
        assert fields["power_on_time"] == "12345"
        assert fields["power_cycle_count"] == "500"
        assert fields["temperature"] == "35"
        assert fields["ata_smart_error_log"] == "0"
        assert fields["self_test_status"] == "Completed without error"

    def test_ssd_rotation_rate_display(self) -> None:
        data = {
            "model_family": "Samsung SSD",
            "model_name": "Samsung SSD 860 EVO",
            "user_capacity": {"bytes": 500107862016},
            "rotation_rate": 0,
            "interface_speed": {"current": {"string": "6.0 Gb/s"}},
            "power_on_time": {"hours": 1000},
            "power_cycle_count": 100,
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

    def test_missing_optional_fields(self) -> None:
        data: dict = {}
        fields = extract_fields(data)
        assert fields["model_family"] == "N/A"
        assert fields["model_name"] == "N/A"
        assert fields["user_capacity_bytes"] == 0
        assert fields["user_capacity_gib"] is None
        assert fields["reallocated_sector_ct"] == "0"
        assert fields["ata_smart_error_log"] == "0"
        assert fields["self_test_status"] == "N/A"


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

    def test_save_and_query(self) -> None:
        conn = init_db(":memory:")

        fields = SmartInfo(
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

    def test_query_with_pattern(self) -> None:
        conn = init_db(":memory:")

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
        save_to_db(conn, "ata-WDC", "/dev/sda", fields, {})
        save_to_db(conn, "ata-Samsung", "/dev/sdb", fields, {})

        rows = query_smart_info(conn, "WDC", None, None)
        assert len(rows) == 1
        assert rows[0]["disk_name"] == "ata-WDC"

        conn.close()
