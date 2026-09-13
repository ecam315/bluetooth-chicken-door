"""Polling coordinator for the BF821 coop door."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import protocol
from .const import (
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .device import BF821Device, BF821Error

_LOGGER = logging.getLogger(__name__)

type BF821ConfigEntry = ConfigEntry[BF821Coordinator]


class BF821Coordinator(DataUpdateCoordinator[protocol.DoorState]):
    """Polls the door and applies desired configuration on every contact.

    The door moves on its own -- on both light and timer triggers -- so the
    last command we sent says nothing about where it is. Real state always
    comes from the status frame.
    """

    def __init__(
        self, hass: HomeAssistant, entry: BF821ConfigEntry, device: BF821Device
    ) -> None:
        minutes = entry.options.get(
            CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {device.name}",
            update_interval=timedelta(minutes=minutes),
            config_entry=entry,
        )
        self.device = device

    async def _async_update_data(self) -> protocol.DoorState:
        try:
            return await self.device.async_poll()
        except BF821Error as err:
            raise UpdateFailed(str(err)) from err

    async def async_send(self, *frames: bytes) -> None:
        """Run a command session and publish the status it returns.

        Raises HomeAssistantError rather than UpdateFailed: this runs from a
        service call, where UpdateFailed surfaces as a traceback instead of a
        readable message.
        """
        try:
            state = await self.device.async_command(*frames)
        except BF821Error as err:
            raise HomeAssistantError(str(err)) from err
        self.async_set_updated_data(state)
