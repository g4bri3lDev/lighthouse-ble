"""The names Home Assistant and scripts import from the package root."""

import lighthouse_ble

EXPECTED = {
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
    "VALVE_COMPANY_ID",
    "Version",
    "create_base_station",
    "discover",
    "parse_advertisement",
    "parse_v1_id",
}


def test_public_api() -> None:
    assert set(lighthouse_ble.__all__) == EXPECTED
    for name in EXPECTED:
        assert hasattr(lighthouse_ble, name), name
