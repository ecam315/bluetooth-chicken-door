"""Tests for the BF821 wire format.

The protocol module has no Home Assistant or Bluetooth imports, so these run
standalone:

    python -m pytest tests/test_protocol.py
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import time
from pathlib import Path

# Loaded straight from the file: importing the package would drag in
# Home Assistant, which these tests deliberately do not need.
_SPEC = importlib.util.spec_from_file_location(
    "bf821_protocol",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "bf821_door"
    / "protocol.py",
)
assert _SPEC is not None and _SPEC.loader is not None
protocol = importlib.util.module_from_spec(_SPEC)
# @dataclass resolves the defining module by name, so register it first.
sys.modules[_SPEC.name] = protocol
_SPEC.loader.exec_module(protocol)

# opened=1, open 06:00:00 enabled, close 18:30:00 disabled, light mode on
FULL_STATUS = bytes.fromhex("5b060106000001121e000001")


class TestEncoding:
    """Frames must go out byte-for-byte as the vendor app builds them."""

    def test_simple_commands(self) -> None:
        assert protocol.get_params() == bytes.fromhex("5a00")
        assert protocol.open_door() == bytes.fromhex("5a01")
        assert protocol.close_door() == bytes.fromhex("5a02")
        assert protocol.pause_door() == bytes.fromhex("5a09")

    def test_toggles(self) -> None:
        assert protocol.set_lamp(True) == bytes.fromhex("5a0a01")
        assert protocol.set_lamp(False) == bytes.fromhex("5a0a00")
        assert protocol.set_auto_by_light(True) == bytes.fromhex("5a0b01")
        assert protocol.set_auto_by_light(False) == bytes.fromhex("5a0b00")

    def test_clock(self) -> None:
        assert protocol.set_clock(6, 30, 15) == bytes.fromhex("5a05061e0f")
        assert protocol.set_clock(23, 59, 59) == bytes.fromhex("5a05173b3b")

    def test_timers(self) -> None:
        assert protocol.set_open_timer(True, time(6, 0, 0)) == bytes.fromhex(
            "5a0301060000"
        )
        assert protocol.set_close_timer(False, time(18, 30, 0)) == bytes.fromhex(
            "5a0400121e00"
        )

    def test_no_checksum_or_length(self) -> None:
        # The write path copies frames verbatim -- if anyone ever adds a
        # length byte or checksum here, the door will silently ignore us.
        assert len(protocol.open_door()) == 2
        assert len(protocol.set_open_timer(True, time(6, 0, 0))) == 6


class TestDecoding:
    def test_rejects_foreign_headers(self) -> None:
        # The vendor app discards anything that is not 0x5B.
        assert protocol.parse(bytes.fromhex("5a01")) is None
        assert protocol.parse(bytes.fromhex("0a01")) is None
        assert protocol.parse(b"") is None
        assert protocol.parse(bytes.fromhex("5b")) is None

    def test_open_close(self) -> None:
        assert protocol.parse(bytes.fromhex("5b01")).opened is True
        assert protocol.parse(bytes.fromhex("5b02")).opened is False

    def test_auto_by_light_acks(self) -> None:
        assert protocol.parse(bytes.fromhex("5b0a")).auto_by_light is True
        assert protocol.parse(bytes.fromhex("5b0b")).auto_by_light is False

    def test_full_status(self) -> None:
        state = protocol.parse(FULL_STATUS)
        assert state is not None
        assert state.opened is True
        assert state.open_timer == time(6, 0, 0)
        assert state.open_timer_on is True
        assert state.close_timer == time(18, 30, 0)
        assert state.close_timer_on is False
        assert state.auto_by_light is True
        assert protocol.is_full_status(FULL_STATUS)

    def test_bare_status_marker_is_recognised(self) -> None:
        # Real BF821 firmware answers a poll with a bare 5B 06 followed by a
        # burst of individual frames, NOT the 12-byte frame the vendor app
        # parses. The marker must count as recognised (empty state), not as
        # an unknown frame, or the burst never starts.
        marker = protocol.parse(bytes.fromhex("5b06"))
        assert marker is not None
        assert marker.opened is None
        assert not protocol.is_full_status(bytes.fromhex("5b06"))

    def test_clock_ack_is_recognised(self) -> None:
        # Observed reply to 5A 05; carries nothing we use.
        ack = protocol.parse(bytes.fromhex("5b050e56de"))
        assert ack is not None
        assert ack.opened is None


class TestRealDeviceBurst:
    """The exact frames captured from the door on first contact."""

    CAPTURE = [
        "5b06",           # burst marker
        "5b01",           # opened
        "5b0b",           # light mode off
        "5b0300000000",   # open timer disabled, 00:00:00
        "5b0400000000",   # close timer disabled, 00:00:00
    ]

    def test_burst_merges_to_complete_state(self) -> None:
        state = protocol.DoorState()
        for frame in self.CAPTURE:
            parsed = protocol.parse(bytes.fromhex(frame))
            assert parsed is not None, f"{frame} must be recognised"
            state = state.merge(parsed)

        assert state.opened is True
        assert state.auto_by_light is False
        assert state.open_timer_on is False
        assert state.close_timer_on is False
        assert state.open_timer == time(0, 0, 0)
        assert state.close_timer == time(0, 0, 0)

    def test_partial_timer_frames(self) -> None:
        state = protocol.parse(bytes.fromhex("5b0301071e00"))
        assert state is not None
        assert state.open_timer_on is True
        assert state.open_timer == time(7, 30, 0)
        assert state.opened is None

    def test_garbage_rtc_does_not_explode(self) -> None:
        # An uninitialised RTC reports out-of-range values; a ValueError here
        # would take down the whole poll.
        state = protocol.parse(bytes.fromhex("5b0301ffffff"))
        assert state is not None
        assert state.open_timer is None
        assert state.open_timer_on is True


class TestMerge:
    def test_partial_frames_do_not_clobber(self) -> None:
        full = protocol.parse(FULL_STATUS)
        assert full is not None
        merged = full.merge(protocol.DoorState(opened=False))
        assert merged.opened is False
        # everything else survives
        assert merged.open_timer == time(6, 0, 0)
        assert merged.auto_by_light is True
