"""Passive advertisement parsing against synthetic and captured payloads."""

from typing import Any

import pytest

from lighthouse_ble.advertisement import parse_advertisement
from lighthouse_ble.models import Version
from tests.helpers import load_json

CASES: list[dict[str, Any]] = load_json("synthetic_advertisements.json") + load_json(
    "captured_advertisements.json"
)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_synthetic_advertisements(case: dict[str, Any]) -> None:
    manufacturer_data = {
        int(company): bytes.fromhex(payload)
        for company, payload in case["manufacturer_data"].items()
    }
    result = parse_advertisement(case["name"], manufacturer_data)
    expected = case["expected"]
    if expected is None:
        assert result is None
        return
    assert result is not None
    assert result.version == expected["version"]
    assert result.name == expected["name"]
    assert result.channel == expected["channel"]
    assert result.power == expected["power"]
    assert result.raw_power == expected["raw_power"]
    assert result.faulty == expected["faulty"]
    raw = expected["raw"]
    assert result.raw == (bytes.fromhex(raw) if raw is not None else None)


def test_bytearray_payload_is_returned_as_bytes() -> None:
    result = parse_advertisement("LHB-1A2B3C4D", {0x055D: bytearray.fromhex("000003000b0000")})
    assert result is not None
    assert type(result.raw) is bytes


def test_v1_ignores_manufacturer_data() -> None:
    result = parse_advertisement("HTC BS 12AB34", {0x055D: bytes.fromhex("000003000b0000")})
    assert result is not None
    assert result.version is Version.V1
    assert result.power is None
