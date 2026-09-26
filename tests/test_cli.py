"""CLI end to end with a replayed scanner and a fake BLE client."""

import pytest
from bleak.backends.device import BLEDevice

from lighthouse_ble.__main__ import format_raw, format_station, main
from lighthouse_ble.const import V2_POWER_UUID
from lighthouse_ble.discovery import DiscoveredStation
from lighthouse_ble.models import LighthouseAdvertisement, PowerState, Version
from tests.fake_ble import (
    V1_DEVICE,
    V2_DEVICE,
    FakeClient,
    Radio,
    advert,
    scanner_with,
    v1_characteristics,
)

ON_CH3_RAW = bytes.fromhex("000003000b0000")
V2_STATION = DiscoveredStation(
    V2_DEVICE,
    LighthouseAdvertisement(Version.V2, "LHB-1A2B3C4D", 3, PowerState.ON, 0x0B, False, ON_CH3_RAW),
    -60,
)
V1_STATION = DiscoveredStation(V1_DEVICE, LighthouseAdvertisement(Version.V1, "HTC BS 12AB34"), -70)


@pytest.fixture
def scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "lighthouse_ble.discovery.BleakScanner",
        scanner_with(
            [
                (V2_DEVICE, advert("LHB-1A2B3C4D", {0x055D: ON_CH3_RAW}, rssi=-60)),
                (V1_DEVICE, advert("HTC BS 12AB34", rssi=-70)),
            ]
        ),
    )


def test_format_station_v2() -> None:
    assert (
        format_station(V2_STATION)
        == "LHB-1A2B3C4D  AA:BB:CC:DD:EE:01  V2  -60 dBm  power=on  channel=3"
    )


def test_format_station_v2_faulty_and_unknown() -> None:
    station = DiscoveredStation(
        V2_DEVICE, LighthouseAdvertisement(Version.V2, None, faulty=True), -61
    )
    assert (
        format_station(station)
        == "(no name)  AA:BB:CC:DD:EE:01  V2  -61 dBm  power=?  channel=?  FAULT"
    )


def test_format_station_v1() -> None:
    assert format_station(V1_STATION) == "HTC BS 12AB34  AA:BB:CC:DD:EE:02  V1  -70 dBm"


def test_format_station_nameless_device() -> None:
    station = DiscoveredStation(
        BLEDevice("AA:BB:CC:DD:EE:08", None, None),
        LighthouseAdvertisement(Version.V2, None),
        -80,
    )
    assert format_station(station).startswith("(no name)  AA:BB:CC:DD:EE:08")


def test_format_raw() -> None:
    first = format_raw(V2_STATION, 1.5, None)
    assert "1.50s" in first
    assert "first" in first
    assert "raw=00 00 03 00 0b 00 00" in first
    assert "+0.25s" in format_raw(V2_STATION, 2.0, 0.25)
    assert "raw=-" in format_raw(V1_STATION, 0.0, None)


@pytest.mark.usefixtures("scanner")
def test_scan(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "scan"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [format_station(V1_STATION), format_station(V2_STATION)]


@pytest.mark.usefixtures("scanner")
def test_scan_raw(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "scan", "--raw"]) == 0
    assert "raw=00 00 03 00 0b 00 00" in capsys.readouterr().out


def test_scan_nothing_found(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("lighthouse_ble.discovery.BleakScanner", scanner_with([]))
    assert main(["--scan-time", "0", "scan"]) == 0
    assert "no base stations found" in capsys.readouterr().out


@pytest.mark.usefixtures("scanner")
def test_on_by_name(radio: Radio, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "on", "lhb-1a2b3c4d"]) == 0
    assert radio.client.writes == [(V2_POWER_UUID, b"\x01", True)]
    assert "LHB-1A2B3C4D: on" in capsys.readouterr().out


@pytest.mark.usefixtures("scanner")
def test_off_by_address(radio: Radio) -> None:
    assert main(["--scan-time", "0", "off", "aa:bb:cc:dd:ee:01"]) == 0
    assert radio.client.writes == [(V2_POWER_UUID, b"\x01", True), (V2_POWER_UUID, b"\x00", True)]


@pytest.mark.usefixtures("scanner")
def test_identify(radio: Radio, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "identify", "LHB-1A2B3C4D"]) == 0
    assert "identifying" in capsys.readouterr().out


@pytest.mark.usefixtures("scanner")
def test_channel(radio: Radio) -> None:
    assert main(["--scan-time", "0", "channel", "LHB-1A2B3C4D", "5"]) == 0
    assert radio.client.writes[-1][1] == b"\x05"


@pytest.mark.usefixtures("scanner")
def test_info_v2(radio: Radio, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "info", "LHB-1A2B3C4D"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "LHB-1A2B3C4D (AA:BB:CC:DD:EE:01, V2)"
    assert "  firmware      1.2.3 build 42" in lines
    assert "  manufacturer  -" in lines
    assert "  power         on" in lines
    assert "  channel       3" in lines
    assert "  standby       yes" in lines


@pytest.mark.usefixtures("scanner")
def test_info_v1(radio: Radio, capsys: pytest.CaptureFixture[str]) -> None:
    radio.client = FakeClient(v1_characteristics())
    assert main(["--scan-time", "0", "info", "HTC BS 12AB34"]) == 0
    out = capsys.readouterr().out
    assert "V1" in out
    assert "power" not in out


@pytest.mark.usefixtures("scanner")
def test_v1_sleep_with_short_id(radio: Radio) -> None:
    radio.client = FakeClient(v1_characteristics())
    assert main(["--scan-time", "0", "off", "HTC BS 12AB34", "--v1-id", "1a2b"]) == 0
    assert radio.client.writes[0][1][:8] == bytes.fromhex("1202000134ab2b1a")


@pytest.mark.usefixtures("scanner")
def test_v1_sleep_without_id_fails(radio: Radio, capsys: pytest.CaptureFixture[str]) -> None:
    radio.client = FakeClient(v1_characteristics())
    assert main(["--scan-time", "0", "off", "HTC BS 12AB34"]) == 1
    assert "back label" in capsys.readouterr().err


@pytest.mark.usefixtures("scanner")
def test_identify_on_v1_fails(radio: Radio, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "identify", "HTC BS 12AB34"]) == 1
    assert "V2" in capsys.readouterr().err
    assert radio.devices == []


@pytest.mark.usefixtures("scanner")
def test_station_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--scan-time", "0", "on", "LHB-FFFFFFFF"]) == 1
    assert "not found" in capsys.readouterr().err


def test_parser_requires_command() -> None:
    with pytest.raises(SystemExit):
        main([])
