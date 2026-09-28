"""Base station devices: short connect -> write -> disconnect sessions over BLE."""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import ClassVar, Final

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .advertisement import parse_advertisement
from .const import (
    CHANNEL_MAX,
    CHANNEL_MIN,
    DIS_FIRMWARE_UUID,
    DIS_HARDWARE_UUID,
    DIS_MANUFACTURER_UUID,
    DIS_MODEL_UUID,
    DIS_SERIAL_UUID,
    V1_POWER_UUID,
    V2_CHANNEL_UUID,
    V2_IDENTIFY_UUID,
    V2_POWER_UUID,
)
from .exceptions import LighthouseConnectionError, MissingV1IdError, UnsupportedError
from .models import BaseStationState, DeviceInfo, LighthouseAdvertisement, PowerState, Version
from .protocol import (
    V1_WAKE_ANY_ID,
    parse_v1_id,
    power_state_from_code,
    v1_power_packet,
    v2_power_writes,
    validate_channel,
)

_LOGGER = logging.getLogger(__name__)

StateCallback = Callable[[BaseStationState], None]

_BLE_ERRORS: Final = (BleakError, TimeoutError)
_IDENTIFY: Final = b"\x01"


def _text(data: bytes) -> str | None:
    """Decode a DIS string: drop NULs, collapse whitespace (firmware contains CRLF)."""
    text = " ".join(data.decode("utf-8", errors="replace").replace("\x00", "").split())
    return text or None


class BaseStation(ABC):
    """Common behaviour of V1 and V2 base stations."""

    version: ClassVar[Version]
    product_name: ClassVar[str]
    manufacturer: ClassVar[str]

    def __init__(
        self, ble_device: BLEDevice, advertisement: LighthouseAdvertisement | None = None
    ) -> None:
        self._ble_device = ble_device
        self._advertised_name: str | None = None
        self._lock = asyncio.Lock()
        self._callbacks: list[StateCallback] = []
        self._state = BaseStationState()
        if advertisement is not None:
            self.update_from_advertisement(advertisement)

    @property
    def address(self) -> str:
        return self._ble_device.address

    @property
    def name(self) -> str:
        return self._advertised_name or self._ble_device.name or self._ble_device.address

    @property
    def state(self) -> BaseStationState:
        return self._state

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Use a newer BLEDevice (e.g. HA switched to a different proxy)."""
        self._ble_device = ble_device

    def update_from_advertisement(self, advertisement: LighthouseAdvertisement) -> None:
        if advertisement.name:
            self._advertised_name = advertisement.name
        self._apply_advertisement(advertisement)

    def _apply_advertisement(self, advertisement: LighthouseAdvertisement) -> None:  # noqa: B027
        """Hook for versions whose advertisements carry state."""

    def register_callback(self, callback: StateCallback) -> Callable[[], None]:
        """Call ``callback`` on every state change; returns an unsubscribe function."""
        self._callbacks.append(callback)

        def unsubscribe() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return unsubscribe

    def _set_state(self, state: BaseStationState) -> None:
        if state == self._state:
            return
        self._state = state
        for callback in list(self._callbacks):
            try:
                callback(state)
            except Exception:
                _LOGGER.exception("State callback for %s failed", self.name)

    @abstractmethod
    async def set_power(self, target: PowerState) -> None:
        """Switch the station to ``target``."""

    async def read_device_info(self) -> DeviceInfo:
        async with self._session() as client:
            model = _text(await self._read(client, DIS_MODEL_UUID))
            serial = _text(await self._read(client, DIS_SERIAL_UUID))
            firmware = _text(await self._read(client, DIS_FIRMWARE_UUID))
            hardware = _text(await self._read(client, DIS_HARDWARE_UUID))
            manufacturer = _text(await self._read(client, DIS_MANUFACTURER_UUID))
        return DeviceInfo(model, serial, firmware, hardware, manufacturer)

    def _current_ble_device(self) -> BLEDevice:
        return self._ble_device

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[BleakClient]:
        """Connect, yield the client, always disconnect. Serialised per device."""
        async with self._lock:
            try:
                client = await establish_connection(
                    BleakClientWithServiceCache,
                    self._ble_device,
                    self.name,
                    ble_device_callback=self._current_ble_device,
                )
            except _BLE_ERRORS as err:
                raise LighthouseConnectionError(f"Could not connect to {self.name}: {err}") from err
            try:
                yield client
            except _BLE_ERRORS as err:
                raise LighthouseConnectionError(
                    f"Communication with {self.name} failed: {err}"
                ) from err
            finally:
                try:
                    await client.disconnect()
                except _BLE_ERRORS as err:
                    _LOGGER.debug("Disconnecting from %s failed: %s", self.name, err)

    async def _write(self, client: BleakClient, uuid: str, data: bytes) -> None:
        char = client.services.get_characteristic(uuid)
        if char is None:
            raise UnsupportedError(f"{self.name} has no characteristic {uuid}")
        await client.write_gatt_char(char, data, response="write" in char.properties)

    async def _read(self, client: BleakClient, uuid: str) -> bytes:
        """Read a characteristic; empty bytes if it is missing or not readable."""
        char = client.services.get_characteristic(uuid)
        if char is None or "read" not in char.properties:
            return b""
        return bytes(await client.read_gatt_char(char))


class BaseStationV2(BaseStation):
    """Valve Index / Lighthouse 2.0 base station."""

    version = Version.V2
    product_name = "Base Station 2.0"
    manufacturer = "Valve"

    def __init__(
        self, ble_device: BLEDevice, advertisement: LighthouseAdvertisement | None = None
    ) -> None:
        self._legacy_firmware: bool | None = None
        super().__init__(ble_device, advertisement)

    @property
    def supports_standby(self) -> bool | None:
        """None until the firmware generation was seen on a connection."""
        return None if self._legacy_firmware is None else not self._legacy_firmware

    def _apply_advertisement(self, advertisement: LighthouseAdvertisement) -> None:
        if advertisement.power is None and advertisement.channel is None:
            return
        self._set_state(
            BaseStationState(
                power=advertisement.power,
                channel=advertisement.channel,
                faulty=advertisement.faulty,
                assumed=False,
            )
        )

    def _detect_firmware(self, client: BleakClient) -> bool:
        """Old firmware exposes the power characteristic without READ. Returns legacy flag."""
        char = client.services.get_characteristic(V2_POWER_UUID)
        if char is None:
            raise UnsupportedError(f"{self.name} has no power characteristic")
        self._legacy_firmware = "read" not in char.properties
        return self._legacy_firmware

    async def set_power(self, target: PowerState) -> None:
        # Validate before connecting; firmware may still turn out to be legacy below.
        v2_power_writes(target, legacy_firmware=bool(self._legacy_firmware))
        async with self._session() as client:
            writes = v2_power_writes(target, legacy_firmware=self._detect_firmware(client))
            for data in writes:
                await self._write(client, V2_POWER_UUID, data)
        self._set_state(replace(self._state, power=target, assumed=True))

    async def identify(self) -> None:
        """Blink the front LED."""
        async with self._session() as client:
            await self._write(client, V2_IDENTIFY_UUID, _IDENTIFY)

    async def set_channel(self, channel: int) -> None:
        validate_channel(channel)
        async with self._session() as client:
            await self._write(client, V2_CHANNEL_UUID, bytes([channel]))
        self._set_state(replace(self._state, channel=channel, assumed=True))

    async def read_state(self) -> BaseStationState:
        """Read power and channel over GATT (fallback when advertisements are not enough)."""
        async with self._session() as client:
            power: PowerState | None = None
            if not self._detect_firmware(client):
                power_data = await self._read(client, V2_POWER_UUID)
                power = power_state_from_code(power_data[0]) if power_data else None
            channel_data = await self._read(client, V2_CHANNEL_UUID)
        channel = (
            channel_data[0]
            if channel_data and CHANNEL_MIN <= channel_data[0] <= CHANNEL_MAX
            else None
        )
        state = BaseStationState(power, channel, self._state.faulty, assumed=False)
        self._set_state(state)
        return state


class BaseStationV1(BaseStation):
    """HTC Vive (Lighthouse 1.0) base station. Its state cannot be read; it is optimistic."""

    version = Version.V1
    product_name = "Base Station 1.0"
    manufacturer = "HTC"

    def __init__(
        self,
        ble_device: BLEDevice,
        advertisement: LighthouseAdvertisement | None = None,
        *,
        station_id: int | None = None,
    ) -> None:
        super().__init__(ble_device, advertisement)
        self.station_id = station_id

    async def set_power(self, target: PowerState) -> None:
        if target is PowerState.SLEEP and self.station_id is None:
            raise MissingV1IdError(
                f"Putting {self.name} to sleep needs the ID printed on its back label"
            )
        station_id = self.station_id if self.station_id is not None else V1_WAKE_ANY_ID
        packet = v1_power_packet(target, station_id)
        async with self._session() as client:
            await self._write(client, V1_POWER_UUID, packet)
        self._set_state(replace(self._state, power=target, assumed=True))


def create_base_station(
    ble_device: BLEDevice,
    advertisement: LighthouseAdvertisement | None = None,
    *,
    v1_id: str | int | None = None,
) -> BaseStation:
    """Build the right BaseStation for a device. ``v1_id`` may be 8 or 4 hex digits."""
    adv = advertisement or parse_advertisement(ble_device.name, {})
    if adv is None:
        raise UnsupportedError(f"{ble_device.name!r} is not a Lighthouse base station")
    if adv.version is Version.V2:
        return BaseStationV2(ble_device, adv)
    if isinstance(v1_id, str):
        station_id: int | None = parse_v1_id(v1_id, adv.name or ble_device.name)
    else:
        station_id = v1_id
    return BaseStationV1(ble_device, adv, station_id=station_id)
