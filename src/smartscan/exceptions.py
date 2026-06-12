"""Custom exception hierarchy for smartscan error handling."""


class SmartScanError(Exception):
    pass


class ConfigError(SmartScanError):
    pass


class DiskNotFoundError(SmartScanError):
    pass


class SmartctlError(SmartScanError):
    pass


class DatabaseError(SmartScanError):
    pass


class InvalidDateError(SmartScanError):
    pass
