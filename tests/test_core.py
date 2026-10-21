from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

import pytest
from conftest import make_fields

from smartscan.database import init_db, parse_date, query_smart_info, save_to_db
from smartscan.exceptions import InvalidDateError
from smartscan.models import ThresholdRules
from smartscan.smartctl import extract_fields, find_disks, find_in_table, run_smartctl, safe_get
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


class TestRunSmartctl:
    def test_uses_xall(self) -> None:
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"smart_status": {"passed": true}}',
        )
        with patch("smartscan.smartctl.subprocess.run", return_value=completed) as run:
            data, returncode = run_smartctl(Path("/dev/sda"))

        assert data == {"smart_status": {"passed": True}}
        assert returncode == 0
        assert run.call_args.args[0] == ["smartctl", "--xall", "--json", "/dev/sda"]

    def test_adds_nvme_link_speed_from_sysfs(self, tmp_path: Path) -> None:
        sysfs = tmp_path / "nvme"
        device = sysfs / "nvme0" / "device"
        device.mkdir(parents=True)
        (device / "current_link_speed").write_text("8.0 GT/s PCIe\n", encoding="utf-8")
        (device / "current_link_width").write_text("4\n", encoding="utf-8")
        completed = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"nvme_smart_health_information_log": {}}',
        )
        with (
            patch("smartscan.smartctl.subprocess.run", return_value=completed),
            patch("smartscan.smartctl._SYSFS_NVME", sysfs),
        ):
            data, _ = run_smartctl(tmp_path / "dev" / "nvme0n1")

        assert data["interface_speed"]["current"]["string"] == "8.0 GT/s PCIe x4"

    def test_adds_seagate_farm_log(self) -> None:
        xall = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"seagate_farm_log": {"supported": true}}',
        )
        farm = CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                '{"seagate_farm_log": {"supported": true, "page_1_drive_information": {"head_flight_hours": 100}}}'
            ),
        )
        with patch("smartscan.smartctl.subprocess.run", side_effect=[xall, farm]) as run:
            data, _ = run_smartctl(Path("/dev/sda"))

        assert data["seagate_farm_log"]["page_1_drive_information"]["head_flight_hours"] == 100
        assert run.call_count == 2
        assert run.call_args_list[1].args[0] == ["smartctl", "-l", "farm", "--json", "/dev/sda"]

    def test_retries_with_sat_for_scsi_without_smart_data(self) -> None:
        scsi = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"device": {"protocol": "SCSI"}}',
        )
        sat = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"device": {"protocol": "ATA"}, "ata_smart_attributes": {"table": []}}',
        )
        with patch("smartscan.smartctl.subprocess.run", side_effect=[scsi, sat]) as run:
            data, _ = run_smartctl(Path("/dev/sda"))

        assert data["device"]["protocol"] == "ATA"
        assert run.call_count == 2
        assert run.call_args_list[1].args[0] == ["smartctl", "--xall", "-d", "sat", "--json", "/dev/sda"]

    def test_does_not_retry_for_scsi_with_smart_data(self) -> None:
        scsi = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"device": {"protocol": "SCSI"}, "scsi_error_counter_log": {}}',
        )
        with patch("smartscan.smartctl.subprocess.run", return_value=scsi) as run:
            data, _ = run_smartctl(Path("/dev/sda"))

        assert data["device"]["protocol"] == "SCSI"
        assert run.call_count == 1


class TestFindDisks:
    def test_includes_scsi_and_skips_partitions(self) -> None:
        class FakeEntry:
            def __init__(self, name: str, target: str) -> None:
                self._name = name
                self._target = target

            def is_symlink(self) -> bool:
                return True

            @property
            def name(self) -> str:
                return self._name

            def resolve(self) -> FakePath:
                return FakePath(self._target)

            def __lt__(self, other: FakeEntry) -> bool:
                return self._name < other._name

        class FakePath:
            def __init__(self, path: str) -> None:
                self._path = path

            def is_dir(self) -> bool:
                return self._path == "/dev/disk/by-id"

            def is_block_device(self) -> bool:
                return not self._path.startswith("/dev/st")

            @property
            def name(self) -> str:
                return self._path.rsplit("/", 1)[-1]

            def iterdir(self) -> list[FakeEntry]:
                return entries

        entries = [
            FakeEntry("ata-Samsung_SSD", "/dev/sdb"),
            FakeEntry("nvme-Micron_7300", "/dev/nvme0n1"),
            FakeEntry("scsi-35000c500abc", "/dev/sda"),
            FakeEntry("scsi-35000c500abc-part1", "/dev/sda1"),
            FakeEntry("scsi-35000c500tape", "/dev/st0"),
            FakeEntry("scsi-35000c500dvd", "/dev/sr0"),
        ]

        with patch("smartscan.smartctl.Path", FakePath):
            disks = find_disks(".*")

        assert [disk.name for disk in disks] == [
            "ata-Samsung_SSD",
            "nvme-Micron_7300",
            "scsi-35000c500abc",
        ]


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
            "ata_smart_data": {"self_test": {"status": {"string": "Completed without error"}}},
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

    def test_extended_error_log_count(self) -> None:
        data = {"ata_smart_error_log": {"extended": {"count": 7}, "summary": {"count": 3}}}
        fields = extract_fields(data)
        assert fields["ata_smart_error_log"] == "7"

    def test_error_log_falls_back_to_summary(self) -> None:
        data = {"ata_smart_error_log": {"summary": {"count": 3}}}
        fields = extract_fields(data)
        assert fields["ata_smart_error_log"] == "3"

    def test_ata_device_statistics_fields(self) -> None:
        data = {
            "logical_block_size": 512,
            "ata_device_statistics": {
                "pages": [
                    {
                        "number": 1,
                        "table": [
                            {"name": "Logical Sectors Written", "value": 2_147_483_648},
                        ],
                    },
                    {
                        "number": 7,
                        "table": [
                            {"name": "Percentage Used Endurance Indicator", "value": 12},
                        ],
                    },
                ]
            },
        }
        fields = extract_fields(data)
        assert fields["endurance_used_percent"] == "12"
        assert fields["data_written_tib"] == pytest.approx(1.0)

    def test_ata_pending_defects_and_phy_counters(self) -> None:
        data = {
            "ata_pending_defects_log": {
                "count": 2,
                "table": [{"lba": 123, "power_on_hours": 1000}],
            },
            "sata_phy_event_counters": {
                "table": [
                    {"id": 0x001, "value": 5},
                    {"id": 0x00A, "value": 3},
                    {"id": 0x00B, "value": 2},
                ]
            },
        }
        fields = extract_fields(data)
        assert fields["pending_defects_count"] == "2"
        assert fields["sata_phy_icrc_errors"] == "5"
        assert fields["sata_phy_crc_errors"] == "2"
        assert fields["sata_phy_comreset_count"] == "3"

    def test_missing_ata_extended_logs(self) -> None:
        fields = extract_fields({})
        assert fields["pending_defects_count"] == "N/A"
        assert fields["sata_phy_icrc_errors"] == "N/A"
        assert fields["sata_phy_crc_errors"] == "N/A"
        assert fields["sata_phy_comreset_count"] == "N/A"

    def test_scsi_health_fields(self) -> None:
        data = {
            "device": {"protocol": "SCSI", "type": "scsi"},
            "scsi_model_name": "SEAGATE ST1200MM0009",
            "scsi_revision": "0001",
            "serial_number": "ABC123",
            "user_capacity": {"bytes": 1_200_000_000_000},
            "rotation_rate": 10000,
            "smart_status": {"passed": True},
            "temperature": {"current": 35},
            "power_on_time": {"hours": 1000},
            "scsi_grown_defect_list": 2,
            "scsi_start_stop_cycle_counter": {
                "accumulated_start_stop_cycles": 42,
                "accumulated_load_unload_cycles": 43,
            },
            "scsi_percentage_used_endurance_indicator": 7,
            "scsi_error_counter_log": {
                "read": {
                    "total_errors_corrected": 10,
                    "total_uncorrected_errors": 1,
                    "gigabytes_processed": "1000.000",
                },
                "write": {
                    "total_errors_corrected": 5,
                    "total_uncorrected_errors": 2,
                    "gigabytes_processed": "2000.000",
                },
                "verify": {
                    "total_errors_corrected": 1,
                    "total_uncorrected_errors": 0,
                    "gigabytes_processed": "0.000",
                },
            },
            "scsi_sas_port_0": {
                "phy_0": {
                    "negotiated logical link rate": "phy enabled; 12 Gbps",
                    "Invalid DWORD count": 3,
                    "Running disparity error count": 4,
                    "Loss of DWORD synchronization count": 5,
                    "Phy reset problem count": 6,
                }
            },
            "scsi_self_test_0": {"result": {"string": "Completed without error"}},
        }
        fields = extract_fields(data)
        assert fields["model_name"] == "SEAGATE ST1200MM0009"
        assert fields["firmware_version"] == "0001"
        assert fields["rotation_rate_display"] == "10000 rpm"
        assert fields["interface_speed"] == "12 Gbps"
        assert fields["power_cycle_count"] == "42"
        assert fields["load_cycle_count"] == "43"
        assert fields["endurance_used_percent"] == "7"
        assert fields["scsi_uncorrected_errors"] == "3"
        assert fields["scsi_corrected_errors"] == "16"
        assert fields["scsi_sas_phy_errors"] == "18"
        assert fields["reallocated_sector_ct"] == "2"
        assert fields["data_written_tib"] == pytest.approx(1.82)
        assert fields["self_test_status"] == "Completed without error"

    def test_scsi_missing_optional_logs(self) -> None:
        data = {"device": {"protocol": "SCSI"}, "smart_status": {"passed": True}}
        fields = extract_fields(data)
        assert fields["model_name"] == "N/A"
        assert fields["scsi_uncorrected_errors"] == "N/A"
        assert fields["scsi_sas_phy_errors"] == "N/A"
        assert fields["interface_speed"] == "N/A"
        assert fields["self_test_status"] == "N/A"

    def test_seagate_ata_farm_fields(self) -> None:
        data = {
            "model_name": "ST6000VX001-2BD186",
            "seagate_farm_log": {
                "supported": True,
                "page_1_drive_information": {
                    "head_flight_hours": 19149,
                    "head_load_events": 5176,
                    "reset_count": 321,
                },
                "page_3_error_statistics": {
                    "number_of_unrecoverable_read_errors": 0,
                    "number_of_unrecoverable_write_errors": 0,
                    "number_of_read_recovery_attempts": 0,
                    "total_crc_errors": 0,
                },
                "page_4_environment_statistics": {"highest_temp": 60},
            },
        }
        fields = extract_fields(data)
        assert fields["farm_unrecoverable_read_errors"] == "0"
        assert fields["farm_unrecoverable_write_errors"] == "0"
        assert fields["farm_read_recovery_attempts"] == "0"
        assert fields["farm_crc_errors"] == "0"
        assert fields["farm_head_flight_hours"] == "19149"
        assert fields["farm_head_load_events"] == "5176"
        assert fields["farm_reset_count"] == "321"
        assert fields["farm_temperature_max"] == "60"

    def test_seagate_sas_farm_fields(self) -> None:
        data = {
            "device": {"protocol": "SCSI"},
            "seagate_farm_log": {
                "supported": True,
                "drive_information": {"hardware_reset_count": 12},
                "error_statistics": {
                    "unrecoverable_read_errors": 1,
                    "unrecoverable_write_errors": 2,
                },
                "environment_statistics": {"highest_temperature": 55},
            },
        }
        fields = extract_fields(data)
        assert fields["farm_unrecoverable_read_errors"] == "1"
        assert fields["farm_unrecoverable_write_errors"] == "2"
        assert fields["farm_reset_count"] == "12"
        assert fields["farm_temperature_max"] == "55"

    def test_nvme_smart_health_fields(self) -> None:
        data = {
            "model_name": "Micron_7300_MTFDHBA960TDF",
            "user_capacity": {"bytes": 960197124096},
            "smart_status": {"passed": True},
            "nvme_smart_health_information_log": {
                "percentage_used": 4,
                "available_spare": 100,
                "data_units_written": 123_456_789,
                "unsafe_shutdowns": 12,
                "power_on_hours": 1000,
                "power_cycles": 20,
                "temperature": 35,
                "media_errors": 0,
                "num_err_log_entries": 0,
            },
            "nvme_self_test_log": {
                "current_self_test_operation": {"string": "No self-test in progress"},
                "table": {"0": {"self_test_result": {"string": "Completed without error"}}},
            },
        }
        fields = extract_fields(data)
        assert fields["endurance_used_percent"] == "4"
        assert fields["available_spare_percent"] == "100"
        assert fields["data_written_tib"] == pytest.approx(57.49)
        assert fields["unsafe_shutdowns"] == "12"
        assert fields["self_test_status"] == "Completed without error"

    def test_nvme_self_test_in_progress(self) -> None:
        data = {
            "nvme_smart_health_information_log": {},
            "nvme_self_test_log": {"current_self_test_operation": {"string": "Short self-test in progress"}},
        }
        fields = extract_fields(data)
        assert fields["self_test_status"] == "Short self-test in progress"

    def test_nvme_self_test_without_log(self) -> None:
        data = {"nvme_smart_health_information_log": {}}
        fields = extract_fields(data)
        assert fields["self_test_status"] == "N/A"

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
            "ata_smart_data": {"self_test": {"status": {"string": "Self-test routine in progress"}}},
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
            "ata_smart_data": {"self_test": {"status": {"string": "Completed without error"}}},
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
        assert any(a.field == "reallocated_sector_ct" and a.level == "warning" for a in alerts)

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
        assert any(a.field == "current_pending_sector" and a.level == "critical" for a in alerts)

    def test_offline_uncorrectable_critical(self) -> None:
        fields = make_fields(offline_uncorrectable="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "offline_uncorrectable" and a.level == "critical" for a in alerts)

    def test_self_test_failure_warning(self) -> None:
        fields = make_fields(self_test_status="Failed in segment 3")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "self_test_status" and a.level == "warning" for a in alerts)

    def test_self_test_healthy(self) -> None:
        fields = make_fields(self_test_status="Completed without error")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert not any(a.field == "self_test_status" for a in alerts)

    def test_self_test_completed_with_failure_is_warning(self) -> None:
        fields = make_fields(self_test_status="Completed: read failure")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "self_test_status" and a.level == "warning" for a in alerts)

    def test_self_test_aborted_is_warning(self) -> None:
        fields = make_fields(self_test_status="Aborted by host")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "self_test_status" and a.level == "warning" for a in alerts)

    def test_self_test_in_progress_is_healthy(self) -> None:
        fields = make_fields(self_test_status="Extended self-test in progress")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert not any(a.field == "self_test_status" for a in alerts)

    def test_endurance_used_warning(self) -> None:
        fields = make_fields(endurance_used_percent="95")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "endurance_used_percent" and a.level == "warning" for a in alerts)

    def test_endurance_used_ok_below_threshold(self) -> None:
        fields = make_fields(endurance_used_percent="50")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert not any(a.field == "endurance_used_percent" for a in alerts)

    def test_pending_defects_critical(self) -> None:
        fields = make_fields(pending_defects_count="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "pending_defects_count" and a.level == "critical" for a in alerts)

    def test_sata_phy_icrc_warning(self) -> None:
        fields = make_fields(sata_phy_icrc_errors="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "sata_phy_icrc_errors" and a.level == "warning" for a in alerts)

    def test_scsi_uncorrected_errors_critical(self) -> None:
        fields = make_fields(scsi_uncorrected_errors="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "scsi_uncorrected_errors" and a.level == "critical" for a in alerts)

    def test_scsi_sas_phy_errors_warning(self) -> None:
        fields = make_fields(scsi_sas_phy_errors="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "scsi_sas_phy_errors" and a.level == "warning" for a in alerts)

    def test_farm_unrecoverable_read_errors_critical(self) -> None:
        fields = make_fields(farm_unrecoverable_read_errors="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "farm_unrecoverable_read_errors" and a.level == "critical" for a in alerts)

    def test_farm_crc_errors_warning(self) -> None:
        fields = make_fields(farm_crc_errors="1")
        rules = ThresholdRules()
        alerts = check_thresholds(fields, rules)
        assert any(a.field == "farm_crc_errors" and a.level == "warning" for a in alerts)

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
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        names = [row["name"] for row in tables]
        assert "smart_info" in names
        conn.close()

    def test_init_db_runs_migrations(self) -> None:
        conn = init_db(":memory:")
        columns = conn.execute("PRAGMA table_info(smart_info)").fetchall()
        col_names = [row["name"] for row in columns]
        assert "smart_status" in col_names
        assert "current_pending_sector" in col_names
        assert "endurance_used_percent" in col_names
        assert "data_written_tib" in col_names
        assert "pending_defects_count" in col_names
        assert "sata_phy_icrc_errors" in col_names
        assert "scsi_uncorrected_errors" in col_names
        assert "farm_unrecoverable_read_errors" in col_names
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
        assert rows[0]["llm_analysis"] == "Drive has 21 reallocated sectors — replace soon."
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

            def resolve(self) -> FakePath:
                return FakePath(self._target)

            def __lt__(self, other: FakeEntry) -> bool:
                return self._name < other._name

        class FakePath:
            def __init__(self, p: str) -> None:
                self._p = p

            def __truediv__(self, other: str) -> FakePath:
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
                "smartscan.smartctl.is_whole_disk",
                side_effect=_mock_is_whole_disk,
            ),
            patch(
                "smartscan.smartctl.get_disk_info",
                side_effect=_mock_get_disk_info,
            ),
        ):
            result = build_device_tree(
                sources=("by-diskseq",),
                exclude_patterns=["^/dev/(loop|zd)\\d+"],
            )

        assert len(result) == 1
        assert result[0]["device"] == "/dev/sda"

    def test_exclude_removes_entire_device_when_any_entry_matches(self) -> None:
        """When any entry for a device matches exclude, the entire device is removed."""
        from smartscan.smartctl import build_device_tree

        class FakeEntry:
            def __init__(self, name: str, target: str, is_symlink: bool = True) -> None:
                self._name = name
                self._target = target
                self._is_symlink = is_symlink

            def is_symlink(self) -> bool:
                return self._is_symlink

            @property
            def name(self) -> str:
                return self._name

            def resolve(self) -> FakePath:
                return FakePath(self._target)

            def __lt__(self, other: FakeEntry) -> bool:
                return self._name < other._name

        class FakePath:
            def __init__(self, p: str) -> None:
                self._p = p

            def __truediv__(self, other: str) -> FakePath:
                return FakePath(f"{self._p}/{other}")

            def is_dir(self) -> bool:
                return self._p in ("/dev/disk", "/dev/disk/by-diskseq")

            def iterdir(self) -> list:
                return entries

            def __str__(self) -> str:
                return self._p

        entries = [
            FakeEntry("ata-Samsung_SSD", "/dev/sda"),
            FakeEntry("ata-BD-RE_Drive", "/dev/sr0"),
            FakeEntry("pci-0000:00:1f.2-ata", "/dev/sr0"),
        ]

        def _mock_is_whole_disk(dev_path: str) -> bool:
            return True

        def _mock_get_disk_info(dev_path: str) -> tuple:
            return "TestModel", "1.0 TiB", 1099511627776

        with (
            patch("smartscan.smartctl.Path", FakePath),
            patch(
                "smartscan.smartctl.is_whole_disk",
                side_effect=_mock_is_whole_disk,
            ),
            patch(
                "smartscan.smartctl.get_disk_info",
                side_effect=_mock_get_disk_info,
            ),
        ):
            result = build_device_tree(
                sources=("by-diskseq",),
                exclude_patterns=["BD-RE"],
            )

        assert len(result) == 1
        assert result[0]["device"] == "/dev/sda"
