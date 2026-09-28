"""Pure protocol encoding/decoding. No I/O; see the design spec, section 2."""

import logging
import re
import struct
from typing import Final

from .const import CHANNEL_MAX, CHANNEL_MIN, V1_NAME_RE
from .exceptions import InvalidChannelError, InvalidV1IdError, MissingV1IdError, UnsupportedError
from .models import PowerState

_LOGGER = logging.getLogger(__name__)

_POWER_CODES: Final[dict[int, PowerState]] = {
    0x00: PowerState.SLEEP,
    0x01: PowerState.BOOTING,
    0x02: PowerState.STANDBY,
    0x03: PowerState.ON,  # awake, firmware too old for standby
    0x08: PowerState.BOOTING,
    0x09: PowerState.BOOTING,
    0x0A: PowerState.BOOTING,
    0x0B: PowerState.ON,
}

SLEEP_TWO_STEP: Final[tuple[bytes, ...]] = (b"\x01", b"\x00")
SLEEP_ONE_STEP: Final[tuple[bytes, ...]] = (b"\x00",)
# Sleep sequence for new-firmware V2 stations. A single 00 is enough (also from standby).
SLEEP_SEQUENCE: tuple[bytes, ...] = SLEEP_ONE_STEP

V1_WAKE_ANY_ID: Final = 0xFFFFFFFF
_V1_MAGIC: Final = 0x12
_HEX8: Final = re.compile(r"[0-9A-F]{8}", re.IGNORECASE)
_HEX4: Final = re.compile(r"[0-9A-F]{4}", re.IGNORECASE)


def power_state_from_code(code: int) -> PowerState:
    """Map a V2 power code (GATT read or advertisement byte 4) to a PowerState."""
    state = _POWER_CODES.get(code)
    if state is None:
        _LOGGER.debug("Unknown V2 power state code 0x%02x", code)
        return PowerState.UNKNOWN
    return state


def v2_power_writes(
    target: PowerState,
    *,
    legacy_firmware: bool,
    sleep_sequence: tuple[bytes, ...] | None = None,
) -> tuple[bytes, ...]:
    """Return the values to write, in order, to the V2 power characteristic."""
    if target is PowerState.ON:
        return (b"\x09",) if legacy_firmware else (b"\x01",)
    if target is PowerState.STANDBY:
        if legacy_firmware:
            raise UnsupportedError("Standby needs newer base station firmware")
        return (b"\x02",)
    if target is PowerState.SLEEP:
        if legacy_firmware:
            return (b"\x00",)
        return sleep_sequence if sleep_sequence is not None else SLEEP_SEQUENCE
    raise UnsupportedError(f"Cannot set power state to {target}")


def validate_channel(channel: int) -> int:
    """Return ``channel`` if it is a valid V2 channel, else raise InvalidChannelError."""
    if not CHANNEL_MIN <= channel <= CHANNEL_MAX:
        raise InvalidChannelError(f"Channel must be {CHANNEL_MIN}-{CHANNEL_MAX}, got {channel}")
    return channel


def parse_v1_id(value: str | None, name: str | None = None) -> int:
    """Parse a V1 station ID from the back label.

    Accepts 8 hex digits, optionally prefixed with ``0x`` and with spaces. Four digits are
    completed with the last four hex digits of the BLE name (``HTC BS XXXXXX``), which always
    match the end of the ID.
    """
    text = (value or "").replace(" ", "")
    if text[:2].lower() == "0x":
        text = text[2:]
    if not text:
        raise MissingV1IdError("V1 base stations need the ID printed on the back label")
    if _HEX4.fullmatch(text):
        if name is None or not V1_NAME_RE.fullmatch(name):
            raise InvalidV1IdError("A 4-digit ID needs the station name to complete it")
        text += name[-4:]
    if not _HEX8.fullmatch(text):
        raise InvalidV1IdError(f"Expected 8 hex digits, got {value!r}")
    return int(text, 16)


def v1_power_packet(target: PowerState, station_id: int) -> bytes:
    """Build the 20-byte V1 power command (spec section 2.4)."""
    if target is PowerState.ON:
        command, timeout = 0x00, 0
    elif target is PowerState.SLEEP:
        command, timeout = 0x02, 1
    else:
        raise UnsupportedError(f"V1 base stations only support on and sleep, not {target}")
    header = struct.pack(">BBH", _V1_MAGIC, command, timeout)
    return header + struct.pack("<I", station_id) + bytes(12)
