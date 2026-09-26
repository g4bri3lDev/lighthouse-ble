"""Parse BLE advertisements into LighthouseAdvertisement.

The V2 payload layout is provisional until confirmed on hardware; the raw payload is always
kept for inspection.
"""

import re
from collections.abc import Mapping
from typing import Final

from .const import (
    CHANNEL_MAX,
    CHANNEL_MIN,
    V1_NAME_RE,
    V1_PLACEHOLDER_NAME,
    V2_NAME_RE,
    V2_PAYLOAD_LENGTH,
    V2_PLACEHOLDER_NAME,
    VALVE_COMPANY_ID,
)
from .models import LighthouseAdvertisement, Version
from .protocol import power_state_from_code

# HA reports the address as the name when no name was received (passive scans).
_ADDRESS_LIKE: Final = re.compile(r"[0-9A-F:-]+", re.IGNORECASE)


def _is_nameless(name: str | None) -> bool:
    return not name or _ADDRESS_LIKE.fullmatch(name) is not None


def parse_advertisement(
    name: str | None, manufacturer_data: Mapping[int, bytes | bytearray]
) -> LighthouseAdvertisement | None:
    """Return what the advertisement says, or None if it is not a Lighthouse base station."""
    if name and V1_NAME_RE.fullmatch(name):
        if name.upper() == V1_PLACEHOLDER_NAME:
            return None
        return LighthouseAdvertisement(Version.V1, name)

    payload = manufacturer_data.get(VALVE_COMPANY_ID)
    raw = bytes(payload) if payload is not None else None

    if name and V2_NAME_RE.fullmatch(name):
        if name.upper() == V2_PLACEHOLDER_NAME:
            return None
        v2_name: str | None = name
    elif _is_nameless(name) and raw is not None and len(raw) == V2_PAYLOAD_LENGTH:
        v2_name = None
    else:
        return None

    if raw is None or len(raw) != V2_PAYLOAD_LENGTH:
        return LighthouseAdvertisement(Version.V2, v2_name, raw=raw)

    channel = raw[2] if CHANNEL_MIN <= raw[2] <= CHANNEL_MAX else None
    return LighthouseAdvertisement(
        Version.V2,
        v2_name,
        channel=channel,
        power=power_state_from_code(raw[4]),
        raw_power=raw[4],
        faulty=raw[6] == 1,
        raw=raw,
    )
