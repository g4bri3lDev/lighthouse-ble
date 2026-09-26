"""discover() with a replayed scanner."""

import pytest
from bleak.backends.device import BLEDevice

from lighthouse_ble.discovery import DiscoveredStation, discover
from lighthouse_ble.models import PowerState, Version
from tests.fake_ble import V1_DEVICE, V2_DEVICE, advert, scanner_with

ON_CH3 = {0x055D: bytes.fromhex("000003000b0000")}
SLEEP_CH3 = {0x055D: bytes.fromhex("00000300000000")}
OTHER = BLEDevice("AA:BB:CC:DD:EE:07", "Pixel 9", None)


async def test_discover_returns_only_lighthouses_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lighthouse_ble.discovery.BleakScanner",
        scanner_with(
            [
                (V2_DEVICE, advert("LHB-1A2B3C4D", ON_CH3, rssi=-55)),
                (OTHER, advert("Pixel 9")),
                (V1_DEVICE, advert("HTC BS 12AB34", rssi=-70)),
            ]
        ),
    )
    stations = await discover(0)
    assert [s.advertisement.name for s in stations] == ["HTC BS 12AB34", "LHB-1A2B3C4D"]
    assert stations[0].advertisement.version is Version.V1
    assert stations[1].rssi == -55
    assert stations[1].device is V2_DEVICE


async def test_latest_advertisement_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lighthouse_ble.discovery.BleakScanner",
        scanner_with(
            [
                (V2_DEVICE, advert("LHB-1A2B3C4D", ON_CH3)),
                (V2_DEVICE, advert("LHB-1A2B3C4D", SLEEP_CH3)),
            ]
        ),
    )
    (station,) = await discover(0)
    assert station.advertisement.power is PowerState.SLEEP


async def test_missing_local_name_falls_back_to_device_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lighthouse_ble.discovery.BleakScanner", scanner_with([(V2_DEVICE, advert(None, ON_CH3))])
    )
    (station,) = await discover(0)
    assert station.advertisement.name == "LHB-1A2B3C4D"


async def test_on_advertisement_sees_every_lighthouse_advert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lighthouse_ble.discovery.BleakScanner",
        scanner_with(
            [
                (V2_DEVICE, advert("LHB-1A2B3C4D", ON_CH3)),
                (OTHER, advert("Pixel 9")),
                (V2_DEVICE, advert("LHB-1A2B3C4D", SLEEP_CH3)),
            ]
        ),
    )
    seen: list[tuple[DiscoveredStation, float]] = []
    await discover(0, on_advertisement=lambda station, ts: seen.append((station, ts)))
    assert [s.advertisement.power for s, _ in seen] == [PowerState.ON, PowerState.SLEEP]
    assert all(isinstance(ts, float) for _, ts in seen)
