"""Async Bluetooth LE control of SteamVR Lighthouse base stations."""

from importlib.metadata import version

from .advertisement import parse_advertisement
from .const import VALVE_COMPANY_ID
from .device import BaseStation, BaseStationV1, BaseStationV2, create_base_station
from .discovery import DiscoveredStation, discover
from .exceptions import (
    InvalidChannelError,
    InvalidV1IdError,
    LighthouseConnectionError,
    LighthouseError,
    MissingV1IdError,
    UnsupportedError,
)
from .models import BaseStationState, DeviceInfo, LighthouseAdvertisement, PowerState, Version
from .protocol import parse_v1_id

__version__ = version("lighthouse-ble")

__all__ = [
    "VALVE_COMPANY_ID",
    "BaseStation",
    "BaseStationState",
    "BaseStationV1",
    "BaseStationV2",
    "DeviceInfo",
    "DiscoveredStation",
    "InvalidChannelError",
    "InvalidV1IdError",
    "LighthouseAdvertisement",
    "LighthouseConnectionError",
    "LighthouseError",
    "MissingV1IdError",
    "PowerState",
    "UnsupportedError",
    "Version",
    "create_base_station",
    "discover",
    "parse_advertisement",
    "parse_v1_id",
]
