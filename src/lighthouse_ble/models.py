"""Value types shared by the whole library."""

from dataclasses import dataclass
from enum import StrEnum


class Version(StrEnum):
    """Base station generation."""

    V1 = "v1"
    V2 = "v2"


class PowerState(StrEnum):
    """Power state of a base station."""

    SLEEP = "sleep"
    STANDBY = "standby"
    BOOTING = "booting"
    ON = "on"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LighthouseAdvertisement:
    """What one BLE advertisement tells us. V2 state fields are provisional (spec 2.1)."""

    version: Version
    name: str | None
    channel: int | None = None
    power: PowerState | None = None
    raw_power: int | None = None
    faulty: bool | None = None
    raw: bytes | None = None


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Device Information Service strings; None when the station does not expose one."""

    model: str | None = None
    serial: str | None = None
    firmware: str | None = None
    hardware: str | None = None
    manufacturer: str | None = None


@dataclass(frozen=True, slots=True)
class BaseStationState:
    """Last known state. ``assumed`` is True when set optimistically after a command."""

    power: PowerState | None = None
    channel: int | None = None
    faulty: bool | None = None
    assumed: bool = False
