"""BaseStationV1 and the factory."""

import pytest
from bleak.backends.device import BLEDevice

from lighthouse_ble.const import V1_POWER_UUID
from lighthouse_ble.device import BaseStationV1, BaseStationV2, create_base_station
from lighthouse_ble.exceptions import MissingV1IdError, UnsupportedError
from lighthouse_ble.models import (
    BaseStationState,
    LighthouseAdvertisement,
    PowerState,
    Version,
)
from tests.fake_ble import V1_DEVICE, V2_DEVICE, FakeClient, Radio, v1_characteristics

STATION_ID = 0x1A2BAB34  # last 4 digits match the name "HTC BS 12AB34"


@pytest.fixture
def v1_radio(radio: Radio) -> Radio:
    radio.client = FakeClient(v1_characteristics())
    return radio


async def test_wake_with_known_id(v1_radio: Radio) -> None:
    station = BaseStationV1(V1_DEVICE, station_id=STATION_ID)
    await station.set_power(PowerState.ON)
    assert v1_radio.client.writes == [
        (V1_POWER_UUID, bytes.fromhex("1200000034ab2b1a" + "00" * 12), True)
    ]
    assert station.state == BaseStationState(power=PowerState.ON, assumed=True)


async def test_wake_without_id_uses_broadcast_id(v1_radio: Radio) -> None:
    await BaseStationV1(V1_DEVICE).set_power(PowerState.ON)
    assert v1_radio.client.writes == [
        (V1_POWER_UUID, bytes.fromhex("12000000ffffffff" + "00" * 12), True)
    ]


async def test_sleep_with_id(v1_radio: Radio) -> None:
    await BaseStationV1(V1_DEVICE, station_id=STATION_ID).set_power(PowerState.SLEEP)
    assert v1_radio.client.writes == [
        (V1_POWER_UUID, bytes.fromhex("1202000134ab2b1a" + "00" * 12), True)
    ]


async def test_sleep_without_id_fails_before_connecting(v1_radio: Radio) -> None:
    with pytest.raises(MissingV1IdError):
        await BaseStationV1(V1_DEVICE).set_power(PowerState.SLEEP)
    assert v1_radio.devices == []


async def test_standby_is_unsupported(v1_radio: Radio) -> None:
    with pytest.raises(UnsupportedError):
        await BaseStationV1(V1_DEVICE, station_id=STATION_ID).set_power(PowerState.STANDBY)
    assert v1_radio.devices == []


async def test_advertisement_keeps_optimistic_state(v1_radio: Radio) -> None:
    station = BaseStationV1(V1_DEVICE, station_id=STATION_ID)
    await station.set_power(PowerState.ON)
    station.update_from_advertisement(LighthouseAdvertisement(Version.V1, "HTC BS 12AB34"))
    assert station.state.power is PowerState.ON


async def test_v1_device_info(v1_radio: Radio) -> None:
    info = await BaseStationV1(V1_DEVICE).read_device_info()
    assert info.serial == "LHB-1A2B3C4D"


def test_v1_has_no_v2_operations() -> None:
    station = BaseStationV1(V1_DEVICE)
    assert station.version is Version.V1
    assert not hasattr(station, "identify")
    assert not hasattr(station, "set_channel")


def test_factory_builds_v2_from_name() -> None:
    assert isinstance(create_base_station(V2_DEVICE), BaseStationV2)


def test_factory_applies_advertised_state() -> None:
    adv = LighthouseAdvertisement(Version.V2, "LHB-1A2B3C4D", channel=4, power=PowerState.ON)
    station = create_base_station(V2_DEVICE, adv)
    assert station.state.channel == 4


def test_factory_builds_nameless_v2_from_advertisement() -> None:
    device = BLEDevice("AA:BB:CC:DD:EE:05", None, None)
    adv = LighthouseAdvertisement(Version.V2, None, channel=4, power=PowerState.ON)
    station = create_base_station(device, adv)
    assert isinstance(station, BaseStationV2)
    assert station.name == "AA:BB:CC:DD:EE:05"


@pytest.mark.parametrize("v1_id", ["1a2b", "1A2BAB34", STATION_ID])
def test_factory_builds_v1_with_id(v1_id: str | int) -> None:
    station = create_base_station(V1_DEVICE, v1_id=v1_id)
    assert isinstance(station, BaseStationV1)
    assert station.station_id == STATION_ID


def test_factory_v1_without_id() -> None:
    station = create_base_station(V1_DEVICE)
    assert isinstance(station, BaseStationV1)
    assert station.station_id is None


def test_factory_rejects_other_devices() -> None:
    with pytest.raises(UnsupportedError):
        create_base_station(BLEDevice("AA:BB:CC:DD:EE:07", "Pixel 9", None))
