"""In-memory stand-ins for bleak so tests never touch Bluetooth."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Self

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError

from lighthouse_ble.const import (
    DIS_FIRMWARE_UUID,
    DIS_HARDWARE_UUID,
    DIS_MODEL_UUID,
    DIS_SERIAL_UUID,
    V1_POWER_UUID,
    V2_CHANNEL_UUID,
    V2_IDENTIFY_UUID,
    V2_POWER_UUID,
)

V2_DEVICE = BLEDevice("AA:BB:CC:DD:EE:01", "LHB-1A2B3C4D", None)
V1_DEVICE = BLEDevice("AA:BB:CC:DD:EE:02", "HTC BS 12AB34", None)


@dataclass
class FakeCharacteristic:
    uuid: str
    properties: list[str]
    value: bytes = b""


class FakeServices:
    def __init__(self, characteristics: list[FakeCharacteristic]) -> None:
        self._by_uuid = {char.uuid: char for char in characteristics}

    def get_characteristic(self, uuid: str) -> FakeCharacteristic | None:
        return self._by_uuid.get(uuid)


@dataclass
class FakeClient:
    """Records writes; ``fail_on_write`` is the index of the write that raises BleakError."""

    characteristics: list[FakeCharacteristic]
    writes: list[tuple[str, bytes, bool]] = field(default_factory=list)
    fail_on_write: int | None = None
    fail_on_disconnect: bool = False
    connected: bool = False
    disconnects: int = 0

    @property
    def services(self) -> FakeServices:
        return FakeServices(self.characteristics)

    async def write_gatt_char(
        self, char: FakeCharacteristic, data: bytes, response: bool | None = None
    ) -> None:
        await asyncio.sleep(0)
        if self.fail_on_write == len(self.writes):
            raise BleakError("write failed")
        self.writes.append((char.uuid, bytes(data), bool(response)))

    async def read_gatt_char(self, char: FakeCharacteristic, **kwargs: Any) -> bytearray:
        await asyncio.sleep(0)
        return bytearray(char.value)

    async def disconnect(self) -> bool:
        self.connected = False
        self.disconnects += 1
        if self.fail_on_disconnect:
            raise BleakError("already disconnected")
        return True


@dataclass
class Radio:
    """Replaces establish_connection; fails loudly if two sessions overlap."""

    client: FakeClient
    connect_error: BaseException | None = None
    devices: list[BLEDevice] = field(default_factory=list)
    callback_devices: list[BLEDevice] = field(default_factory=list)

    async def establish(
        self, client_class: type[Any], device: BLEDevice, name: str, **kwargs: Any
    ) -> FakeClient:
        self.devices.append(device)
        callback = kwargs.get("ble_device_callback")
        if callback is not None:
            self.callback_devices.append(callback())
        if self.connect_error is not None:
            raise self.connect_error
        assert not self.client.connected, "two BLE sessions overlapped"
        self.client.connected = True
        await asyncio.sleep(0)
        return self.client


def dis_characteristics() -> list[FakeCharacteristic]:
    """Synthetic DIS strings (real contents unverified, spec section 8); no manufacturer."""
    return [
        FakeCharacteristic(DIS_MODEL_UUID, ["read"], b"Valve Base Station 2.0"),
        FakeCharacteristic(DIS_SERIAL_UUID, ["read"], b"LHB-1A2B3C4D"),
        FakeCharacteristic(DIS_FIRMWARE_UUID, ["read"], b"1.2.3\r\nbuild 42\x00"),
        FakeCharacteristic(DIS_HARDWARE_UUID, ["read"], b"rev B"),
    ]


def v2_characteristics(
    *, legacy: bool = False, power: bytes = b"\x0b", channel: bytes = b"\x03"
) -> list[FakeCharacteristic]:
    power_props = ["write"] if legacy else ["read", "write", "notify"]
    return [
        FakeCharacteristic(V2_POWER_UUID, power_props, power),
        FakeCharacteristic(V2_CHANNEL_UUID, ["read", "write", "notify"], channel),
        FakeCharacteristic(V2_IDENTIFY_UUID, ["write"]),
        *dis_characteristics(),
    ]


def v1_characteristics() -> list[FakeCharacteristic]:
    return [FakeCharacteristic(V1_POWER_UUID, ["write"]), *dis_characteristics()]


def advert(
    name: str | None, manufacturer_data: dict[int, bytes] | None = None, rssi: int = -60
) -> AdvertisementData:
    return AdvertisementData(
        local_name=name,
        manufacturer_data=manufacturer_data or {},
        service_data={},
        service_uuids=[],
        tx_power=None,
        rssi=rssi,
        platform_data=(),
    )


def scanner_with(adverts: list[tuple[BLEDevice, AdvertisementData]]) -> type[Any]:
    """A BleakScanner replacement that replays ``adverts`` when entered."""

    class FakeScanner:
        def __init__(
            self,
            detection_callback: Callable[[BLEDevice, AdvertisementData], None],
            **kwargs: Any,
        ) -> None:
            self._callback = detection_callback

        async def __aenter__(self) -> Self:
            for device, data in adverts:
                self._callback(device, data)
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    return FakeScanner
