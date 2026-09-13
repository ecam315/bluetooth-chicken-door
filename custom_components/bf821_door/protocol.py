"""Frame encoding and decoding for the BF821 coop door.

Pure functions -- no Home Assistant or Bluetooth imports -- so the wire format
can be exercised in isolation. Recovered from com.zhicase.petdoor 1.1.1;
see apk-re/PROTOCOL.md for the provenance of every constant here.

Frames are written verbatim: no length byte, no checksum, no wrapping.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

TX_HEADER = 0x5A
RX_HEADER = 0x5B

# TX command bytes
CMD_GET_PARAMS = 0x00
CMD_OPEN = 0x01
CMD_CLOSE = 0x02
CMD_SET_OPEN_TIMER = 0x03
CMD_SET_CLOSE_TIMER = 0x04
CMD_SET_CLOCK = 0x05
CMD_PAUSE = 0x09
CMD_LAMP = 0x0A
CMD_AUTO_BY_LIGHT = 0x0B

# RX type bytes
RX_OPENED = 0x01
RX_CLOSED = 0x02
RX_OPEN_TIMER = 0x03
RX_CLOSE_TIMER = 0x04
RX_FULL_STATUS = 0x06
RX_AUTO_BY_LIGHT_ON = 0x0A
RX_AUTO_BY_LIGHT_OFF = 0x0B

FULL_STATUS_LEN = 12


@dataclass(frozen=True, slots=True)
class DoorState:
    """A snapshot of everything the door reports.

    Every field is optional because partial frames (0x5B 0x01 etc.) update
    only one attribute. ``None`` means "not reported by this frame".
    """

    opened: bool | None = None
    open_timer_on: bool | None = None
    open_timer: time | None = None
    close_timer_on: bool | None = None
    close_timer: time | None = None
    auto_by_light: bool | None = None

    def merge(self, other: DoorState) -> DoorState:
        """Overlay ``other`` onto self, ignoring its unreported fields."""
        return DoorState(
            opened=other.opened if other.opened is not None else self.opened,
            open_timer_on=(
                other.open_timer_on
                if other.open_timer_on is not None
                else self.open_timer_on
            ),
            open_timer=(
                other.open_timer if other.open_timer is not None else self.open_timer
            ),
            close_timer_on=(
                other.close_timer_on
                if other.close_timer_on is not None
                else self.close_timer_on
            ),
            close_timer=(
                other.close_timer if other.close_timer is not None else self.close_timer
            ),
            auto_by_light=(
                other.auto_by_light
                if other.auto_by_light is not None
                else self.auto_by_light
            ),
        )


def _frame(*payload: int) -> bytes:
    return bytes((TX_HEADER, *payload))


def get_params() -> bytes:
    """Ask for the full status frame."""
    return _frame(CMD_GET_PARAMS)


def open_door() -> bytes:
    return _frame(CMD_OPEN)


def close_door() -> bytes:
    return _frame(CMD_CLOSE)


def pause_door() -> bytes:
    return _frame(CMD_PAUSE)


def set_lamp(on: bool) -> bytes:
    """Toggle the unit's lamp. Note: the door never reports this back."""
    return _frame(CMD_LAMP, 1 if on else 0)


def set_auto_by_light(on: bool) -> bytes:
    """Toggle light mode (open above ~300 lux, close below ~100 lux)."""
    return _frame(CMD_AUTO_BY_LIGHT, 1 if on else 0)


def set_clock(hour: int, minute: int, second: int) -> bytes:
    """Set the door's RTC. Volatile -- resend whenever we reconnect."""
    return _frame(CMD_SET_CLOCK, hour, minute, second)


def set_open_timer(on: bool, value: time) -> bytes:
    return _frame(
        CMD_SET_OPEN_TIMER, 1 if on else 0, value.hour, value.minute, value.second
    )


def set_close_timer(on: bool, value: time) -> bytes:
    return _frame(
        CMD_SET_CLOSE_TIMER, 1 if on else 0, value.hour, value.minute, value.second
    )


def _safe_time(hour: int, minute: int, second: int) -> time | None:
    """Build a time, tolerating the garbage an uninitialised RTC reports."""
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)


def parse(data: bytes) -> DoorState | None:
    """Decode one notification frame.

    Returns ``None`` for anything unrecognised -- the door emits frames with
    other headers (0x5A, 0x0A, 0x5C) that the vendor app also discards.
    """
    if len(data) < 2 or data[0] != RX_HEADER:
        return None

    kind = data[1]

    if kind == RX_OPENED:
        return DoorState(opened=True)
    if kind == RX_CLOSED:
        return DoorState(opened=False)
    if kind == RX_AUTO_BY_LIGHT_ON:
        return DoorState(auto_by_light=True)
    if kind == RX_AUTO_BY_LIGHT_OFF:
        return DoorState(auto_by_light=False)

    if kind == RX_OPEN_TIMER and len(data) >= 6:
        return DoorState(
            open_timer_on=data[2] == 1,
            open_timer=_safe_time(data[3], data[4], data[5]),
        )
    if kind == RX_CLOSE_TIMER and len(data) >= 6:
        return DoorState(
            close_timer_on=data[2] == 1,
            close_timer=_safe_time(data[3], data[4], data[5]),
        )

    if kind == RX_FULL_STATUS and len(data) >= FULL_STATUS_LEN:
        return DoorState(
            opened=data[2] == 1,
            open_timer=_safe_time(data[3], data[4], data[5]),
            open_timer_on=data[6] == 1,
            close_timer=_safe_time(data[7], data[8], data[9]),
            close_timer_on=data[10] == 1,
            auto_by_light=data[11] == 1,
        )

    return None


def is_full_status(data: bytes) -> bool:
    """True if this frame is the complete status reply to ``get_params()``."""
    return (
        len(data) >= FULL_STATUS_LEN
        and data[0] == RX_HEADER
        and data[1] == RX_FULL_STATUS
    )
