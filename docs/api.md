# API Reference

## CLI

::: smartscan.cli
    options:
      members:
        - create_parser
        - main

## Smartctl

::: smartscan.smartctl
    options:
      members:
        - find_disks
        - run_smartctl
        - extract_fields
        - safe_get
        - find_in_table
        - check_smartctl_error

## Database

::: smartscan.database
    options:
      members:
        - init_db
        - open_db
        - save_to_db
        - query_smart_info
        - parse_date

## Output

::: smartscan.output
    options:
      members:
        - print_table
        - print_query_table
        - print_json_output
        - row_to_fields

## Configuration

::: smartscan.config
    options:
      members:
        - load_config

## Data Models

::: smartscan.models
    options:
      members:
        - SmartScanConfig
        - SmartInfo

## Exceptions

::: smartscan.exceptions
    options:
      members:
        - SmartScanError
        - ConfigError
        - DiskNotFoundError
        - SmartctlError
        - DatabaseError
        - InvalidDateError
