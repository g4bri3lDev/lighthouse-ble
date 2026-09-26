"""Shared fixtures."""

import pytest

from tests.fake_ble import FakeClient, Radio, v2_characteristics


@pytest.fixture
def radio(monkeypatch: pytest.MonkeyPatch) -> Radio:
    radio = Radio(FakeClient(v2_characteristics()))
    monkeypatch.setattr("lighthouse_ble.device.establish_connection", radio.establish)
    return radio
