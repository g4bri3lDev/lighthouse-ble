"""Models, constants and the exception hierarchy."""

from dataclasses import FrozenInstanceError

import pytest

import lighthouse_ble
from lighthouse_ble.const import V1_NAME_RE, V2_NAME_RE, VALVE_COMPANY_ID
from lighthouse_ble.exceptions import (
    InvalidChannelError,
    InvalidV1IdError,
    LighthouseConnectionError,
    LighthouseError,
    MissingV1IdError,
    UnsupportedError,
)
from lighthouse_ble.models import (
    BaseStationState,
    DeviceInfo,
    LighthouseAdvertisement,
    PowerState,
    Version,
)


def test_package_version() -> None:
    assert lighthouse_ble.__version__ == "0.0.0"


def test_power_state_values_are_stable_strings() -> None:
    assert [state.value for state in PowerState] == ["sleep", "standby", "booting", "on", "unknown"]


def test_version_values() -> None:
    assert Version.V1.value == "v1"
    assert Version.V2.value == "v2"


def test_state_defaults_to_nothing_known() -> None:
    assert BaseStationState() == BaseStationState(
        power=None, channel=None, faulty=None, assumed=False
    )


def test_models_are_frozen() -> None:
    state = BaseStationState()
    with pytest.raises(FrozenInstanceError):
        state.power = PowerState.ON  # type: ignore[misc]


def test_advertisement_defaults() -> None:
    adv = LighthouseAdvertisement(Version.V1, "HTC BS 12AB34")
    assert (adv.channel, adv.power, adv.raw_power, adv.faulty, adv.raw) == (None,) * 5


def test_device_info_defaults() -> None:
    assert DeviceInfo() == DeviceInfo(None, None, None, None, None)


@pytest.mark.parametrize(
    "error",
    [
        LighthouseConnectionError,
        UnsupportedError,
        InvalidChannelError,
        MissingV1IdError,
        InvalidV1IdError,
    ],
)
def test_all_errors_share_a_base(error: type[Exception]) -> None:
    assert issubclass(error, LighthouseError)


def test_value_errors_are_value_errors() -> None:
    assert issubclass(InvalidChannelError, ValueError)
    assert issubclass(InvalidV1IdError, ValueError)


def test_valve_company_id() -> None:
    assert VALVE_COMPANY_ID == 1373


@pytest.mark.parametrize("name", ["LHB-1A2B3C4D", "lhb-1a2b3c4d"])
def test_v2_name_pattern(name: str) -> None:
    assert V2_NAME_RE.fullmatch(name)


@pytest.mark.parametrize("name", ["LHB-1A2B3C4", "LHB-1A2B3C4DX", "XLHB-1A2B3C4D"])
def test_v2_name_pattern_rejects(name: str) -> None:
    assert V2_NAME_RE.fullmatch(name) is None


def test_v1_name_pattern() -> None:
    assert V1_NAME_RE.fullmatch("HTC BS 12AB34")
    assert V1_NAME_RE.fullmatch("HTC BS 12AB3") is None
