"""Command-line interface: lighthouse-ble / python -m lighthouse_ble."""

import argparse
import asyncio
import sys
import time

from .device import BaseStation, BaseStationV2, create_base_station
from .discovery import DiscoveredStation, discover
from .exceptions import LighthouseError, UnsupportedError
from .models import PowerState, Version

_POWER_COMMANDS = {"on": PowerState.ON, "off": PowerState.SLEEP, "standby": PowerState.STANDBY}
_YES_NO = {None: None, True: "yes", False: "no"}


def format_station(station: DiscoveredStation) -> str:
    """One line per station for ``scan``."""
    adv = station.advertisement
    fields = [
        adv.name or "(no name)",
        station.device.address,
        adv.version.value.upper(),
        f"{station.rssi} dBm",
    ]
    if adv.version is Version.V2:
        fields.append(f"power={adv.power.value if adv.power else '?'}")
        fields.append(f"channel={adv.channel if adv.channel is not None else '?'}")
        if adv.faulty:
            fields.append("FAULT")
    return "  ".join(fields)


def format_raw(station: DiscoveredStation, elapsed: float, interval: float | None) -> str:
    """One line per advertisement for ``scan --raw``."""
    adv = station.advertisement
    raw = adv.raw.hex(" ") if adv.raw is not None else "-"
    gap = f"+{interval:.2f}s" if interval is not None else "first"
    name = adv.name or station.device.address
    return f"{elapsed:8.2f}s  {gap:>8}  {name}  rssi={station.rssi}  raw={raw}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lighthouse-ble")
    parser.add_argument(
        "--scan-time", type=float, default=10.0, help="seconds to scan (default: 10)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="list nearby base stations")
    scan.add_argument("--raw", action="store_true", help="print every advertisement with raw bytes")
    station_help = "BLE address or name (LHB-... / HTC BS ...)"
    commands.add_parser("info", help="read device information and state").add_argument(
        "station", help=station_help
    )
    for command, target in _POWER_COMMANDS.items():
        power = commands.add_parser(command, help=f"switch to {target.value}")
        power.add_argument("station", help=station_help)
        power.add_argument(
            "--v1-id", help="V1 only: ID from the back label (8 or the first 4 hex digits)"
        )
    commands.add_parser("identify", help="blink the LED (V2)").add_argument(
        "station", help=station_help
    )
    channel = commands.add_parser("channel", help="set the channel (V2)")
    channel.add_argument("station", help=station_help)
    channel.add_argument("channel", type=int, help="1-16")
    return parser


async def _scan(args: argparse.Namespace) -> int:
    start = time.monotonic()
    last_seen: dict[str, float] = {}

    def on_advertisement(station: DiscoveredStation, timestamp: float) -> None:
        if not args.raw:
            return
        previous = last_seen.get(station.device.address)
        last_seen[station.device.address] = timestamp
        interval = None if previous is None else timestamp - previous
        print(format_raw(station, timestamp - start, interval), flush=True)

    stations = await discover(args.scan_time, on_advertisement=on_advertisement)
    if not stations:
        print("no base stations found")
    for station in stations:
        print(format_station(station))
    return 0


async def _resolve(identifier: str, scan_time: float) -> DiscoveredStation:
    wanted = identifier.lower()
    for station in await discover(scan_time):
        name = (station.advertisement.name or "").lower()
        if wanted in (station.device.address.lower(), name):
            return station
    raise LighthouseError(f"{identifier} not found within {scan_time:g} s")


def _require_v2(station: BaseStation) -> BaseStationV2:
    if not isinstance(station, BaseStationV2):
        raise UnsupportedError(f"{station.name}: only V2 base stations support this")
    return station


async def _info(station: BaseStation) -> int:
    info = await station.read_device_info()
    print(f"{station.name} ({station.address}, {station.version.value.upper()})")
    rows = [
        ("model", info.model),
        ("serial", info.serial),
        ("firmware", info.firmware),
        ("hardware", info.hardware),
        ("manufacturer", info.manufacturer),
    ]
    if isinstance(station, BaseStationV2):
        state = await station.read_state()
        rows += [
            ("power", state.power.value if state.power else None),
            ("channel", str(state.channel) if state.channel is not None else None),
            ("standby", _YES_NO[station.supports_standby]),
        ]
    for label, value in rows:
        print(f"  {label:13} {value or '-'}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    if args.command == "scan":
        return await _scan(args)
    found = await _resolve(args.station, args.scan_time)
    station = create_base_station(
        found.device, found.advertisement, v1_id=getattr(args, "v1_id", None)
    )
    if args.command == "info":
        return await _info(station)
    if args.command in _POWER_COMMANDS:
        target = _POWER_COMMANDS[args.command]
        await station.set_power(target)
        print(f"{station.name}: {target.value}")
    elif args.command == "identify":
        await _require_v2(station).identify()
        print(f"{station.name}: identifying")
    elif args.command == "channel":
        await _require_v2(station).set_channel(args.channel)
        print(f"{station.name}: channel {args.channel}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point."""
    args = _parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except LighthouseError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
