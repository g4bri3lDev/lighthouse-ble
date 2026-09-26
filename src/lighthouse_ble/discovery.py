"""Standalone scanning (CLI and scripts). Home Assistant supplies devices itself."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from .advertisement import parse_advertisement
from .models import LighthouseAdvertisement


@dataclass(frozen=True, slots=True)
class DiscoveredStation:
    """A base station seen while scanning, with its latest advertisement."""

    device: BLEDevice
    advertisement: LighthouseAdvertisement
    rssi: int


AdvertisementCallback = Callable[[DiscoveredStation, float], None]


async def discover(
    scan_time: float = 10.0, *, on_advertisement: AdvertisementCallback | None = None
) -> list[DiscoveredStation]:
    """Scan for ``scan_time`` seconds and return every base station seen.

    ``on_advertisement`` is called for every base station advertisement with a
    ``time.monotonic()`` timestamp.
    """
    found: dict[str, DiscoveredStation] = {}

    def detected(device: BLEDevice, data: AdvertisementData) -> None:
        advertisement = parse_advertisement(data.local_name or device.name, data.manufacturer_data)
        if advertisement is None:
            return
        station = DiscoveredStation(device, advertisement, data.rssi)
        found[device.address] = station
        if on_advertisement is not None:
            on_advertisement(station, time.monotonic())

    async with BleakScanner(detection_callback=detected):
        await asyncio.sleep(scan_time)
    return sorted(found.values(), key=lambda s: s.advertisement.name or s.device.address)
