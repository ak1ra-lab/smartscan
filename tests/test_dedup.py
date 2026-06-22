"""Tests for the dedup module: change detection and record compaction."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from conftest import make_fields

from smartscan.database import init_db, save_to_db
from smartscan.dedup import (
    MONITORED_FIELDS,
    _field_changed,
    compact_rows,
    find_redundant_ids,
    has_significant_change,
)
from smartscan.fields import TIME_SERIES_FIELDS


class TestFieldChanged:
    def test_same_string_no_change(self) -> None:
        prev = make_fields(reallocated_sector_ct="5")
        curr = make_fields(reallocated_sector_ct="5")
        assert not _field_changed(prev, curr, "reallocated_sector_ct")

    def test_different_string_change(self) -> None:
        prev = make_fields(reallocated_sector_ct="0")
        curr = make_fields(reallocated_sector_ct="5")
        assert _field_changed(prev, curr, "reallocated_sector_ct")

    def test_temperature_small_delta_ignored(self) -> None:
        prev = make_fields(temperature="30")
        curr = make_fields(temperature="32")
        assert not _field_changed(prev, curr, "temperature")

    def test_temperature_large_delta_detected(self) -> None:
        prev = make_fields(temperature="30")
        curr = make_fields(temperature="34")
        assert _field_changed(prev, curr, "temperature")

    def test_temperature_exact_threshold_boundary(self) -> None:
        prev = make_fields(temperature="30")
        curr = make_fields(temperature="33.0")
        assert not _field_changed(prev, curr, "temperature")

        prev = make_fields(temperature="30")
        curr = make_fields(temperature="33.1")
        assert _field_changed(prev, curr, "temperature")

    def test_temperature_na_fallback_string_compare(self) -> None:
        prev = make_fields(temperature="N/A")
        curr = make_fields(temperature="35")
        assert _field_changed(prev, curr, "temperature")

    def test_smart_status_change(self) -> None:
        prev = make_fields(smart_status="PASSED")
        curr = make_fields(smart_status="FAILED")
        assert _field_changed(prev, curr, "smart_status")


class TestHasSignificantChange:
    def test_identical_records_no_change(self) -> None:
        prev = make_fields()
        curr = make_fields()
        assert not has_significant_change(prev, curr)

    def test_any_monitored_field_triggers_change(self) -> None:
        prev = make_fields(reallocated_sector_ct="0")
        curr = make_fields(reallocated_sector_ct="1")
        assert has_significant_change(prev, curr)

    def test_temperature_within_delta_no_change(self) -> None:
        prev = make_fields(temperature="30")
        curr = make_fields(temperature="32")
        assert not has_significant_change(prev, curr)

    def test_time_series_fields_ignored(self) -> None:
        prev = make_fields(power_on_time="100")
        curr = make_fields(power_on_time="200")
        assert not has_significant_change(prev, curr)

    def test_time_series_field_set_membership(self) -> None:
        assert "power_on_time" in TIME_SERIES_FIELDS
        assert "power_cycle_count" in TIME_SERIES_FIELDS
        assert "load_cycle_count" in TIME_SERIES_FIELDS
        assert "power_off_retract_count" in TIME_SERIES_FIELDS
        assert "reallocated_sector_ct" not in TIME_SERIES_FIELDS

    def test_monitored_field_set_membership(self) -> None:
        assert "smart_status" in MONITORED_FIELDS
        assert "temperature" in MONITORED_FIELDS
        assert "reallocated_sector_ct" in MONITORED_FIELDS
        assert "current_pending_sector" in MONITORED_FIELDS
        assert "offline_uncorrectable" in MONITORED_FIELDS
        assert "helium_level" in MONITORED_FIELDS
        assert "power_on_time" not in MONITORED_FIELDS


class TestCompactRows:
    def _make_row(
        self,
        row_id: int,
        disk_path: str,
        timestamp: str,
        smart_status: str = "PASSED",
        temperature: str = "30",
        reallocated: str = "0",
        power_on_time: str = "100",
    ) -> sqlite3.Row:
        conn = init_db(":memory:")
        conn.execute(
            "INSERT INTO smart_info (id, timestamp, disk_name, disk_path, "
            "smart_status, temperature_celsius, reallocated_sector_ct, "
            "power_on_time_hours, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row_id,
                timestamp,
                disk_path,
                disk_path,
                smart_status,
                temperature,
                reallocated,
                power_on_time,
                "{}",
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM smart_info WHERE id=?", (row_id,)).fetchone()
        conn.close()
        return row

    def test_single_row_returns_itself(self) -> None:
        row = self._make_row(1, "/dev/sda", "2024-01-01T00:00:00Z")
        result = compact_rows([row], 30)
        assert len(result) == 1
        assert result[0]["id"] == 1

    def test_no_significant_change_within_window_keeps_newest(self) -> None:
        r1 = self._make_row(1, "/dev/sda", "2024-01-01T00:00:00Z")
        r2 = self._make_row(2, "/dev/sda", "2024-01-01T00:10:00Z")
        result = compact_rows([r1, r2], 30)
        assert len(result) == 1
        assert result[0]["id"] == 2

    def test_change_within_window_keeps_both(self) -> None:
        r1 = self._make_row(1, "/dev/sda", "2024-01-01T00:00:00Z", reallocated="0")
        r2 = self._make_row(2, "/dev/sda", "2024-01-01T00:10:00Z", reallocated="5")
        result = compact_rows([r1, r2], 30)
        assert len(result) == 2
        assert [r["id"] for r in result] == [1, 2]

    def test_outside_window_keeps_both(self) -> None:
        r1 = self._make_row(1, "/dev/sda", "2024-01-01T00:00:00Z")
        r2 = self._make_row(2, "/dev/sda", "2024-01-01T01:00:00Z")
        result = compact_rows([r1, r2], 30)
        assert len(result) == 2

    def test_chain_three_unchanged_keeps_last(self) -> None:
        r1 = self._make_row(1, "/dev/sda", "2024-01-01T00:00:00Z")
        r2 = self._make_row(2, "/dev/sda", "2024-01-01T00:10:00Z")
        r3 = self._make_row(3, "/dev/sda", "2024-01-01T00:20:00Z")
        result = compact_rows([r1, r2, r3], 30)
        assert len(result) == 1
        assert result[0]["id"] == 3

    def test_middle_change_splits_cluster(self) -> None:
        r1 = self._make_row(1, "/dev/sda", "2024-01-01T00:00:00Z", reallocated="0")
        r2 = self._make_row(2, "/dev/sda", "2024-01-01T00:10:00Z", reallocated="5")
        r3 = self._make_row(3, "/dev/sda", "2024-01-01T00:20:00Z", reallocated="5")
        result = compact_rows([r1, r2, r3], 30)
        assert len(result) == 2
        assert [r["id"] for r in result] == [1, 3]

    def test_time_series_change_ignored(self) -> None:
        conn = init_db(":memory:")
        conn.execute(
            "INSERT INTO smart_info (id, timestamp, disk_name, disk_path, "
            "smart_status, temperature_celsius, reallocated_sector_ct, "
            "power_on_time_hours, raw_json) VALUES "
            "(1, '2024-01-01T00:00:00Z', 'sda', '/dev/sda', 'PASSED', '30', '0', '100', '{}'), "
            "(2, '2024-01-01T00:10:00Z', 'sda', '/dev/sda', 'PASSED', '30', '0', '200', '{}')"
        )
        conn.commit()
        rows = conn.execute("SELECT * FROM smart_info ORDER BY id").fetchall()
        result = compact_rows(rows, 30)
        conn.close()
        assert len(result) == 1
        assert result[0]["id"] == 2


class TestFindRedundantIds:
    def test_no_redundant_records(self) -> None:
        conn = init_db(":memory:")

        fields = make_fields()
        save_to_db(conn, "sda", "/dev/sda", fields, {})

        ids = find_redundant_ids(conn, ".*", 30)
        assert ids == []
        conn.close()

    def test_two_identical_records_within_window(self) -> None:
        conn = init_db(":memory:")

        now = datetime.now(timezone.utc)
        ts1 = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        ts2 = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        cols = (
            "timestamp, disk_name, disk_path, smart_status, temperature_celsius, "
            "reallocated_sector_ct, current_pending_sector, offline_uncorrectable, "
            "reallocated_event_count, ata_smart_error_log_count, self_test_status, "
            "udma_crc_error_count, raw_read_error_rate, spin_retry_count, "
            "power_off_retract_count, load_cycle_count, helium_level, "
            "raw_json"
        )
        vals = "'PASSED', '30', '0', '0', '0', '0', '0', '', '0', '0', '0', '0', '0', '0', '{}'"

        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES (1, '{ts1}', 'sda', '/dev/sda', {vals})"
        )
        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES (2, '{ts2}', 'sda', '/dev/sda', {vals})"
        )
        conn.commit()

        ids = find_redundant_ids(conn, ".*", 30)
        assert ids == [1]
        conn.close()

    def test_significant_change_keeps_both(self) -> None:
        conn = init_db(":memory:")

        now = datetime.now(timezone.utc)
        ts1 = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        ts2 = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        cols = (
            "timestamp, disk_name, disk_path, smart_status, temperature_celsius, "
            "reallocated_sector_ct, current_pending_sector, offline_uncorrectable, "
            "reallocated_event_count, ata_smart_error_log_count, self_test_status, "
            "udma_crc_error_count, raw_read_error_rate, spin_retry_count, "
            "power_off_retract_count, load_cycle_count, helium_level, "
            "raw_json"
        )

        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES "
            f"(1, '{ts1}', 'sda', '/dev/sda', 'PASSED', '30', '0', '0', '0', '0', "
            f"'0', '', '0', '0', '0', '0', '0', '0', '{{}}')"
        )
        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES "
            f"(2, '{ts2}', 'sda', '/dev/sda', 'PASSED', '30', '5', '0', '0', '0', "
            f"'0', '', '0', '0', '0', '0', '0', '0', '{{}}')"
        )
        conn.commit()

        ids = find_redundant_ids(conn, ".*", 30)
        assert ids == []
        conn.close()

    def test_pattern_filter_applies(self) -> None:
        conn = init_db(":memory:")

        now = datetime.now(timezone.utc)
        ts1 = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        ts2 = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        cols = (
            "timestamp, disk_name, disk_path, smart_status, temperature_celsius, "
            "reallocated_sector_ct, current_pending_sector, offline_uncorrectable, "
            "reallocated_event_count, ata_smart_error_log_count, self_test_status, "
            "udma_crc_error_count, raw_read_error_rate, spin_retry_count, "
            "power_off_retract_count, load_cycle_count, helium_level, "
            "raw_json"
        )
        vals = "'PASSED', '30', '0', '0', '0', '0', '0', '', '0', '0', '0', '0', '0', '0', '{}'"

        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES "
            f"(1, '{ts1}', 'ata-WDC', '/dev/sda', {vals})"
        )
        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES "
            f"(2, '{ts2}', 'ata-WDC', '/dev/sda', {vals})"
        )
        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES "
            f"(3, '{ts1}', 'ata-Samsung', '/dev/sdb', {vals})"
        )
        conn.execute(
            f"INSERT INTO smart_info (id, {cols}) VALUES "
            f"(4, '{ts2}', 'ata-Samsung', '/dev/sdb', {vals})"
        )
        conn.commit()

        ids = find_redundant_ids(conn, "WDC", 30)
        assert ids == [1]

        conn.close()
