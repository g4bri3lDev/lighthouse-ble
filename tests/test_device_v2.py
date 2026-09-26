"""BaseStationV2 against a fake BLE client."""

import asyncio

import pytest
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from lighthouse_ble.const import V2_CHANNEL_UUID, V2_IDENTIFY_UUID, V2_POWER_UUID
from lighthouse_ble.device import BaseStationV2
from lighthouse_ble.exceptions import (
    InvalidChannelError,
    LighthouseConnectionError,
    UnsupportedError,
)
from lighthouse_ble.models import (
    BaseStationState,
    DeviceInfo,
    LighthouseAdvertisement,
    PowerState,
    Version,
)
from tests.fake_ble import V2_DEVICE, FakeCharacteristic, FakeClient, Radio, v2_characteristics

P, CH, ID = V2_POWER_UUID, V2_CHANNEL_UUID, V2_IDENTIFY_UUID


def adv(
    power: PowerState | None = None, channel: int | None = None, faulty: bool | None = None
) -> LighthouseAdvertisement:
    return LighthouseAdvertisement(
        Version.V2, "LHB-1A2B3C4D", channel=channel, power=power, faulty=faulty
    )


ON_CH3 = adv(PowerState.ON, 3, False)


# --- passive state -------------------------------------------------------------------------


def test_starts_with_unknown_state() -> None:
    station = BaseStationV2(V2_DEVICE)
    assert station.state == BaseStationState()
    assert station.name == "LHB-1A2B3C4D"
    assert station.address == "AA:BB:CC:DD:EE:01"
    assert station.version is Version.V2
    assert station.supports_standby is None


def test_initial_advertisement_sets_state() -> None:
    station = BaseStationV2(V2_DEVICE, ON_CH3)
    assert station.state == BaseStationState(PowerState.ON, 3, False, assumed=False)


def test_advertisement_without_state_keeps_state() -> None:
    station = BaseStationV2(V2_DEVICE, ON_CH3)
    station.update_from_advertisement(adv())
    assert station.state.power is PowerState.ON


def test_name_falls_back_to_address() -> None:
    station = BaseStationV2(BLEDevice("AA:BB:CC:DD:EE:09", None, None))
    assert station.name == "AA:BB:CC:DD:EE:09"


def test_advertised_name_wins_over_missing_ble_name() -> None:
    station = BaseStationV2(BLEDevice("AA:BB:CC:DD:EE:09", None, None), ON_CH3)
    assert station.name == "LHB-1A2B3C4D"


def test_callbacks_fire_only_on_change() -> None:
    station = BaseStationV2(V2_DEVICE)
    seen: list[BaseStationState] = []
    unsubscribe = station.register_callback(seen.append)
    station.update_from_advertisement(ON_CH3)
    station.update_from_advertisement(ON_CH3)
    assert seen == [BaseStationState(PowerState.ON, 3, False)]
    unsubscribe()
    unsubscribe()  # idempotent
    station.update_from_advertisement(adv(PowerState.SLEEP, 3, False))
    assert len(seen) == 1


def test_failing_callback_does_not_block_others(caplog: pytest.LogCaptureFixture) -> None:
    station = BaseStationV2(V2_DEVICE)
    seen: list[BaseStationState] = []

    def boom(state: BaseStationState) -> None:
        raise RuntimeError("entity broke")

    station.register_callback(boom)
    station.register_callback(seen.append)
    station.update_from_advertisement(ON_CH3)
    assert len(seen) == 1
    assert station.state.power is PowerState.ON
    assert "callback" in caplog.text


# --- power -----------------------------------------------------------------------------------


async def test_set_power_on_new_firmware(radio: Radio) -> None:
    station = BaseStationV2(V2_DEVICE)
    await station.set_power(PowerState.ON)
    assert radio.client.writes == [(P, b"\x01", True)]
    assert station.state == BaseStationState(power=PowerState.ON, assumed=True)
    assert station.supports_standby is True
    assert radio.client.disconnects == 1


async def test_sleep_uses_two_step_sequence(radio: Radio) -> None:
    await BaseStationV2(V2_DEVICE).set_power(PowerState.SLEEP)
    assert radio.client.writes == [(P, b"\x01", True), (P, b"\x00", True)]


async def test_standby(radio: Radio) -> None:
    await BaseStationV2(V2_DEVICE).set_power(PowerState.STANDBY)
    assert radio.client.writes == [(P, b"\x02", True)]


async def test_optimistic_power_keeps_advertised_fields(radio: Radio) -> None:
    station = BaseStationV2(V2_DEVICE, ON_CH3)
    await station.set_power(PowerState.SLEEP)
    assert station.state == BaseStationState(PowerState.SLEEP, 3, False, assumed=True)


async def test_legacy_firmware_wake_and_sleep(radio: Radio) -> None:
    radio.client = FakeClient(v2_characteristics(legacy=True))
    station = BaseStationV2(V2_DEVICE)
    await station.set_power(PowerState.ON)
    await station.set_power(PowerState.SLEEP)
    assert radio.client.writes == [(P, b"\x09", True), (P, b"\x00", True)]
    assert station.supports_standby is False


async def test_standby_on_known_legacy_firmware_fails_before_connecting(radio: Radio) -> None:
    radio.client = FakeClient(v2_characteristics(legacy=True))
    station = BaseStationV2(V2_DEVICE)
    await station.set_power(PowerState.SLEEP)
    connects = len(radio.devices)
    with pytest.raises(UnsupportedError):
        await station.set_power(PowerState.STANDBY)
    assert len(radio.devices) == connects


async def test_standby_on_undetected_legacy_firmware_fails_without_writing(radio: Radio) -> None:
    radio.client = FakeClient(v2_characteristics(legacy=True))
    station = BaseStationV2(V2_DEVICE)
    with pytest.raises(UnsupportedError):
        await station.set_power(PowerState.STANDBY)
    assert radio.client.writes == []
    assert radio.client.disconnects == 1
    assert station.state == BaseStationState()


@pytest.mark.parametrize("target", [PowerState.BOOTING, PowerState.UNKNOWN])
async def test_cannot_target_transient_states(radio: Radio, target: PowerState) -> None:
    with pytest.raises(UnsupportedError):
        await BaseStationV2(V2_DEVICE).set_power(target)
    assert radio.devices == []


# --- identify / channel ------------------------------------------------------------------


async def test_identify(radio: Radio) -> None:
    await BaseStationV2(V2_DEVICE).identify()
    assert radio.client.writes == [(ID, b"\x01", True)]


async def test_write_without_response_when_only_option(radio: Radio) -> None:
    radio.client = FakeClient([FakeCharacteristic(ID, ["write-without-response"])])
    await BaseStationV2(V2_DEVICE).identify()
    assert radio.client.writes == [(ID, b"\x01", False)]


async def test_missing_characteristic_is_unsupported(radio: Radio) -> None:
    radio.client = FakeClient([])
    with pytest.raises(UnsupportedError):
        await BaseStationV2(V2_DEVICE).identify()
    assert radio.client.disconnects == 1


async def test_missing_power_characteristic_is_unsupported(radio: Radio) -> None:
    radio.client = FakeClient([])
    with pytest.raises(UnsupportedError):
        await BaseStationV2(V2_DEVICE).set_power(PowerState.ON)


async def test_set_channel(radio: Radio) -> None:
    station = BaseStationV2(V2_DEVICE, ON_CH3)
    await station.set_channel(7)
    assert radio.client.writes == [(CH, b"\x07", True)]
    assert station.state == BaseStationState(PowerState.ON, 7, False, assumed=True)


@pytest.mark.parametrize("channel", [0, 17])
async def test_invalid_channel_fails_before_connecting(radio: Radio, channel: int) -> None:
    with pytest.raises(InvalidChannelError):
        await BaseStationV2(V2_DEVICE).set_channel(channel)
    assert radio.devices == []


# --- reads ---------------------------------------------------------------------------------


async def test_read_state_new_firmware(radio: Radio) -> None:
    radio.client = FakeClient(v2_characteristics(power=b"\x02", channel=b"\x05\x00\x00\x00"))
    station = BaseStationV2(V2_DEVICE, adv(PowerState.ON, 3, True))
    state = await station.read_state()
    assert state == BaseStationState(PowerState.STANDBY, 5, True, assumed=False)
    assert station.state == state
    assert radio.client.writes == []


async def test_read_state_legacy_firmware_has_no_power(radio: Radio) -> None:
    radio.client = FakeClient(v2_characteristics(legacy=True))
    state = await BaseStationV2(V2_DEVICE).read_state()
    assert state == BaseStationState(power=None, channel=3)


async def test_read_state_empty_values(radio: Radio) -> None:
    radio.client = FakeClient(v2_characteristics(power=b"", channel=b""))
    state = await BaseStationV2(V2_DEVICE).read_state()
    assert state == BaseStationState()


async def test_read_device_info(radio: Radio) -> None:
    info = await BaseStationV2(V2_DEVICE).read_device_info()
    assert info == DeviceInfo(
        model="Valve Base Station 2.0",
        serial="LHB-1A2B3C4D",
        firmware="1.2.3 build 42",
        hardware="rev B",
        manufacturer=None,
    )


# --- connection handling -------------------------------------------------------------------


@pytest.mark.parametrize("error", [BleakError("out of slots"), TimeoutError()])
async def test_connect_failure_raises_connection_error_and_keeps_state(
    radio: Radio, error: BaseException
) -> None:
    radio.connect_error = error
    station = BaseStationV2(V2_DEVICE)
    with pytest.raises(LighthouseConnectionError):
        await station.set_power(PowerState.ON)
    assert station.state == BaseStationState()


async def test_failure_mid_sequence_disconnects_and_keeps_state(radio: Radio) -> None:
    radio.client.fail_on_write = 1
    station = BaseStationV2(V2_DEVICE)
    with pytest.raises(LighthouseConnectionError):
        await station.set_power(PowerState.SLEEP)
    assert radio.client.writes == [(P, b"\x01", True)]
    assert radio.client.disconnects == 1
    assert station.state == BaseStationState()


async def test_disconnect_error_does_not_mask_success(radio: Radio) -> None:
    radio.client.fail_on_disconnect = True
    station = BaseStationV2(V2_DEVICE)
    await station.set_power(PowerState.ON)
    assert station.state.power is PowerState.ON


async def test_operations_are_serialised(radio: Radio) -> None:
    station = BaseStationV2(V2_DEVICE)
    await asyncio.gather(
        station.set_channel(1), station.identify(), station.set_power(PowerState.ON)
    )
    assert len(radio.client.writes) == 3


async def test_reconnect_uses_latest_ble_device(radio: Radio) -> None:
    station = BaseStationV2(V2_DEVICE)
    newer = BLEDevice("AA:BB:CC:DD:EE:01", "LHB-1A2B3C4D", {"via": "proxy"})
    station.set_ble_device(newer)
    await station.identify()
    assert radio.devices[-1] is newer
    assert radio.callback_devices[-1] is newer
