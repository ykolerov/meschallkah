"""Conservative USB-UART port discovery for the D1 TMC2209.

Only probe likely CP210x interfaces; prove the connected chip is a TMC2209 by
reading IOIN.VERSION == 0x21. Detection never configures the driver, writes a
register, or requests motor movement. An explicit --port bypasses detection.
"""
from __future__ import annotations

import sys

from serial.tools import list_ports

from tmc2209_uart import TMC2209


def is_cp210x(info) -> bool:
    """Identify the existing CP2102 or another explicitly identified CP210x."""
    if getattr(info, "vid", None) == 0x10C4 and getattr(info, "pid", None) == 0xEA60:
        return True
    fields = ("description", "manufacturer", "product", "hwid")
    return any("cp210" in str(getattr(info, field, "") or "").lower()
               for field in fields)


def candidate_ports(comports=None):
    """USB serial interfaces likely to be CP210x; sorted by port name."""
    if comports is None:
        comports = list_ports.comports()
    return sorted((port for port in comports if is_cp210x(port)),
                  key=lambda p: p.device)


def probe_tmc2209(port: str, baud: int = 115200) -> bool:
    """Read the TMC2209 IOIN register, without writing to the driver."""
    device = TMC2209(port=port, baud=baud, marker="none", timeout=0.3)
    try:
        return device.check_connection() == 0x21
    finally:
        device.close()


def resolve_port(*, baud: int = 115200, comports=None, probe=None,
                 interactive=None, input_fn=input, output_fn=print) -> str:
    """Return a verified port or raise ValueError with actionable instructions.

    Multiple verified devices are numbered for interactive selection. A
    noninteractive invocation never guesses and requires explicit --port.
    """
    if probe is None:
        probe = lambda port: probe_tmc2209(port, baud=baud)
    candidates = candidate_ports(comports)
    if not candidates:
        raise ValueError(
            "No CP210x USB-UART adapter found. Connect your CP2102 and install "
            "the Silicon Labs VCP driver if needed. Inspect ports with "
            "'python -m serial.tools.list_ports -v'; for other adapters use --port COMx."
        )

    good, problems = [], []
    for info in candidates:
        try:
            if probe(info.device):
                good.append(info)
            else:
                problems.append(info.device + ": wrong TMC chip version")
        except Exception as exc:
            problems.append(info.device + ": " + str(exc))

    if not good:
        raise ValueError(
            "CP210x found but no connected TMC2209 responded with version 0x21. "
            "Check 24 V VM, 3.3 V VIO, TX/RX/PDN_UART wiring and the hardware "
            "EN switch. Details: " + "; ".join(problems) +
            ". Use --port COMx to specify a port manually."
        )

    if len(good) == 1:
        chosen = good[0]
        output_fn("Auto-detected %s (%s); TMC2209 verified (0x21)." %
                  (chosen.device, chosen.description or "CP210x"))
        return chosen.device

    output_fn("Multiple CP210x adapters with verified TMC2209 detected:")
    for index, info in enumerate(good, start=1):
        output_fn("  %d. %s — %s" % (index, info.device, info.description or "CP210x"))

    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive:
        raise ValueError(
            "Multiple TMC2209 devices found. Specify --port explicitly: " +
            ", ".join(info.device for info in good)
        )
    for _ in range(3):
        try:
            response = input_fn("Select device number (or q to cancel): ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise ValueError("Port selection cancelled. Use --port COMx.") from exc
        if response.lower() in ("q", "quit"):
            raise ValueError("Port selection cancelled. Use --port COMx.")
        if response.isdecimal() and 1 <= int(response) <= len(good):
            chosen = good[int(response) - 1]
            output_fn("Selected %s; TMC2209 verified (0x21)." % chosen.device)
            return chosen.device
        output_fn("Invalid choice.")
    raise ValueError("No valid port selected; use --port COMx.")
