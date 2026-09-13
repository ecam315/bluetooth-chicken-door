"""BLE session handling for the BF821 coop door.

Deliberately connects, talks, and disconnects for every interaction rather
than holding the link:

* the door is solar powered and a held connection costs meaningfully more
  than advertising;
* it accepts exactly one BLE link, and a wedged link on a single-link
  peripheral may need a physical power cycle at a coop nobody is standing
  next to. Each connect/disconnect cycle is self-healing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from . import protocol
from .const import (
    NOTIFY_UUID,
    STATUS_SETTLE,
    STATUS_TIMEOUT,
    WRITE_GAP,
    WRITE_UUID,
)

_LOGGER = logging.getLogger(__name__)


class BF821Error(Exception):
    """Raised when a session with the door fails."""


class BF821Device:
    """Owns all BLE traffic to one door."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address.upper()
        self.name = name
        # Serialises sessions: the door only accepts one link at a time, and
        # a poll racing a command would fight over it.
        self._lock = asyncio.Lock()

    async def async_poll(self) -> protocol.DoorState:
        """Connect, read status, disconnect."""
        return await self._async_session(())

    async def async_command(self, *writes: bytes) -> protocol.DoorState:
        """Connect, send commands, read back status, disconnect."""
        return await self._async_session(writes)

    async def _async_session(
        self, writes: Sequence[bytes]
    ) -> protocol.DoorState:
        async with self._lock:
            return await self._async_session_locked(writes)

    async def _async_session_locked(
        self, writes: Sequence[bytes]
    ) -> protocol.DoorState:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            raise BF821Error(
                f"{self.name} ({self.address}) is not in range of any "
                "Bluetooth adapter or proxy"
            )

        loop = asyncio.get_running_loop()
        state = protocol.DoorState()
        first_frame = asyncio.Event()
        last_rx = 0.0

        def _on_notify(_char: BleakGATTCharacteristic, data: bytearray) -> None:
            nonlocal state, last_rx
            raw = bytes(data)
            _LOGGER.debug("%s: notify %s", self.name, raw.hex(" "))
            parsed = protocol.parse(raw)
            if parsed is None:
                _LOGGER.debug("%s: ignoring unknown frame %s", self.name, raw.hex(" "))
                return
            state = state.merge(parsed)
            last_rx = loop.time()
            first_frame.set()

        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                use_services_cache=True,
            )
        except (BleakError, asyncio.TimeoutError) as err:
            raise BF821Error(f"could not connect to {self.name}: {err}") from err

        try:
            write_char = client.services.get_characteristic(WRITE_UUID)
            if write_char is None:
                raise BF821Error(
                    f"{self.name} does not expose the write characteristic "
                    f"{WRITE_UUID}"
                )
            # The vendor app picks the write type from the characteristic's
            # properties rather than assuming; do the same, since the live
            # GATT table has not been dumped yet.
            with_response = "write-without-response" not in write_char.properties

            await client.start_notify(NOTIFY_UUID, _on_notify)

            # The RTC is wiped whenever the solar panel loses power, so the
            # clock is re-sent on every single connection rather than being
            # assumed to have persisted.
            now = dt_util.now()
            await self._write(
                client, write_char, with_response,
                protocol.set_clock(now.hour, now.minute, now.second),
            )

            for frame in writes:
                await self._write(client, write_char, with_response, frame)

            await self._write(
                client, write_char, with_response, protocol.get_params()
            )

            try:
                async with asyncio.timeout(STATUS_TIMEOUT):
                    await first_frame.wait()
            except TimeoutError as err:
                raise BF821Error(
                    f"{self.name} did not answer the status request within "
                    f"{STATUS_TIMEOUT:.0f}s"
                ) from err

            # The reply is a burst of separate frames; it is complete once
            # the door has gone quiet for a moment.
            while (quiet := STATUS_SETTLE - (loop.time() - last_rx)) > 0:
                await asyncio.sleep(quiet)

            if state.opened is None:
                raise BF821Error(
                    f"{self.name} replied but never reported a door position"
                )
            return state
        except BleakError as err:
            raise BF821Error(f"{self.name} session failed: {err}") from err
        finally:
            try:
                await client.disconnect()
            except BleakError as err:
                # A clean disconnect matters: an aborted one wedges the
                # proxy's scanner. Log loudly but never mask the real error.
                _LOGGER.warning("%s: error during disconnect: %s", self.name, err)

    async def _write(
        self,
        client: BleakClientWithServiceCache,
        char: BleakGATTCharacteristic,
        with_response: bool,
        frame: bytes,
    ) -> None:
        _LOGGER.debug("%s: write %s", self.name, frame.hex(" "))
        await client.write_gatt_char(char, frame, response=with_response)
        # Back-to-back frames get dropped by the firmware.
        await asyncio.sleep(WRITE_GAP)
