# lighthouse-ble

Async Bluetooth LE control of SteamVR Lighthouse base stations — Valve Index (V2, `LHB-…`) and
HTC Vive (V1, `HTC BS …`). Built to back a Home Assistant integration, usable on its own.

| | V2 (Valve Index) | V1 (HTC Vive) |
|---|---|---|
| Power | on / standby / sleep | on / sleep |
| State | passive from advertisements (provisional), or GATT read | not readable (optimistic) |
| Identify (blink LED) | yes | — |
| Channel 1–16 | read / write | — |

> **Provisional:** decoding V2 state from advertisements has not been confirmed on hardware yet.
> The raw payload is always exposed as `LighthouseAdvertisement.raw` so mismatches are visible.

## Install

```bash
pip install lighthouse-ble
```

## Command line

```bash
lighthouse-ble scan                      # list stations with passive state
lighthouse-ble scan --raw                # every advertisement with raw bytes and intervals
lighthouse-ble info LHB-1A2B3C4D         # device information + GATT state
lighthouse-ble on LHB-1A2B3C4D
lighthouse-ble standby LHB-1A2B3C4D
lighthouse-ble off LHB-1A2B3C4D
lighthouse-ble identify LHB-1A2B3C4D
lighthouse-ble channel LHB-1A2B3C4D 5
lighthouse-ble off "HTC BS 12AB34" --v1-id 1A2B   # V1: first 4 hex digits from the back label
```

Stations can be addressed by name or BLE address. `--scan-time` changes how long to look
(default 10 s).

## Library

```python
import asyncio

from lighthouse_ble import PowerState, create_base_station, discover


async def main() -> None:
    for found in await discover(5):
        station = create_base_station(found.device, found.advertisement)
        print(station.name, station.state)
        await station.set_power(PowerState.ON)


asyncio.run(main())
```

In Home Assistant, feed advertisements from the bluetooth integration instead of scanning:

```python
adv = parse_advertisement(service_info.name, service_info.manufacturer_data)
station.set_ble_device(service_info.device)
station.update_from_advertisement(adv)
unsubscribe = station.register_callback(lambda state: ...)
```

Every command opens a short connection and disconnects again, so no ESPHome proxy slot stays
taken. Errors are always `LighthouseError` subclasses.

## Development

```bash
uv sync
uv run pytest --cov=lighthouse_ble
uv run mypy
uv run ruff check . && uv run ruff format --check .
```

## License

Apache-2.0
