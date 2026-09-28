"""Pure protocol encoding and decoding."""

import pytest

from lighthouse_ble.exceptions import (
    InvalidChannelError,
    InvalidV1IdError,
    MissingV1IdError,
    UnsupportedError,
)
from lighthouse_ble.models import PowerState
from lighthouse_ble.protocol import (
    SLEEP_ONE_STEP,
    SLEEP_SEQUENCE,
    SLEEP_TWO_STEP,
    V1_WAKE_ANY_ID,
    parse_v1_id,
    power_state_from_code,
    v1_power_packet,
    v2_power_writes,
    validate_channel,
)


@pytest.mark.parametrize(
    ("code", "state"),
    [
        (0x00, PowerState.SLEEP),
        (0x01, PowerState.BOOTING),
        (0x02, PowerState.STANDBY),
        (0x03, PowerState.ON),
        (0x08, PowerState.BOOTING),
        (0x09, PowerState.BOOTING),
        (0x0A, PowerState.BOOTING),
        (0x0B, PowerState.ON),
        (0x04, PowerState.UNKNOWN),
        (0xFF, PowerState.UNKNOWN),
    ],
)
def test_power_state_from_code(code: int, state: PowerState) -> None:
    assert power_state_from_code(code) is state


def test_unknown_power_code_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("DEBUG", logger="lighthouse_ble.protocol"):
        power_state_from_code(0x42)
    assert "0x42" in caplog.text


def test_default_sleep_sequence_is_one_step() -> None:
    assert SLEEP_SEQUENCE == SLEEP_ONE_STEP == (b"\x00",)
    assert SLEEP_TWO_STEP == (b"\x01", b"\x00")


@pytest.mark.parametrize(
    ("target", "writes"),
    [
        (PowerState.ON, (b"\x01",)),
        (PowerState.STANDBY, (b"\x02",)),
        (PowerState.SLEEP, (b"\x00",)),
    ],
)
def test_v2_power_writes_new_firmware(target: PowerState, writes: tuple[bytes, ...]) -> None:
    assert v2_power_writes(target, legacy_firmware=False) == writes


def test_v2_sleep_two_step_variant() -> None:
    assert v2_power_writes(
        PowerState.SLEEP, legacy_firmware=False, sleep_sequence=SLEEP_TWO_STEP
    ) == (b"\x01", b"\x00")


@pytest.mark.parametrize(
    ("target", "writes"),
    [(PowerState.ON, (b"\x09",)), (PowerState.SLEEP, (b"\x00",))],
)
def test_v2_power_writes_legacy_firmware(target: PowerState, writes: tuple[bytes, ...]) -> None:
    assert v2_power_writes(target, legacy_firmware=True) == writes


def test_v2_standby_unsupported_on_legacy_firmware() -> None:
    with pytest.raises(UnsupportedError):
        v2_power_writes(PowerState.STANDBY, legacy_firmware=True)


@pytest.mark.parametrize("target", [PowerState.BOOTING, PowerState.UNKNOWN])
def test_v2_cannot_target_transient_states(target: PowerState) -> None:
    with pytest.raises(UnsupportedError):
        v2_power_writes(target, legacy_firmware=False)


@pytest.mark.parametrize("channel", [1, 8, 16])
def test_validate_channel_accepts(channel: int) -> None:
    assert validate_channel(channel) == channel


@pytest.mark.parametrize("channel", [0, 17, -1])
def test_validate_channel_rejects(channel: int) -> None:
    with pytest.raises(InvalidChannelError):
        validate_channel(channel)


@pytest.mark.parametrize(
    "value", ["1A2BAB34", "1a2bab34", "0x1A2BAB34", " 1A2B AB34 ", "0X1a2bab34"]
)
def test_parse_v1_id_full(value: str) -> None:
    assert parse_v1_id(value) == 0x1A2BAB34


@pytest.mark.parametrize("value", ["1A2B", "1a2b", " 1a2b "])
def test_parse_v1_id_completes_from_name(value: str) -> None:
    assert parse_v1_id(value, "HTC BS 12AB34") == 0x1A2BAB34


def test_parse_v1_id_short_without_name_is_invalid() -> None:
    with pytest.raises(InvalidV1IdError):
        parse_v1_id("1A2B")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_parse_v1_id_missing(value: str | None) -> None:
    with pytest.raises(MissingV1IdError):
        parse_v1_id(value, "HTC BS 12AB34")


@pytest.mark.parametrize("value", ["1A2B3", "ZZZZZZZZ", "1A2BAB34FF"])
def test_parse_v1_id_invalid(value: str) -> None:
    with pytest.raises(InvalidV1IdError):
        parse_v1_id(value, "HTC BS 12AB34")


def test_v1_wake_packet() -> None:
    assert v1_power_packet(PowerState.ON, 0xAABBCCDD) == bytes.fromhex(
        "12000000ddccbbaa" + "00" * 12
    )


def test_v1_sleep_packet() -> None:
    assert v1_power_packet(PowerState.SLEEP, 0xAABBCCDD) == bytes.fromhex(
        "12020001ddccbbaa" + "00" * 12
    )


def test_v1_packet_is_20_bytes() -> None:
    assert len(v1_power_packet(PowerState.ON, V1_WAKE_ANY_ID)) == 20


@pytest.mark.parametrize("target", [PowerState.STANDBY, PowerState.BOOTING, PowerState.UNKNOWN])
def test_v1_unsupported_targets(target: PowerState) -> None:
    with pytest.raises(UnsupportedError):
        v1_power_packet(target, 0xAABBCCDD)
