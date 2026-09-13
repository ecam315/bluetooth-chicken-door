"""Cover platform for the BF821 coop door."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import (
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import protocol
from .const import MOTION_TIMEOUT, POST_COMMAND_REFRESH
from .coordinator import BF821ConfigEntry, BF821Coordinator
from .entity import BF821Entity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BF821ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the door cover."""
    async_add_entities([BF821Cover(entry.runtime_data)])


class BF821Cover(BF821Entity, CoverEntity):
    """The coop door itself."""

    _attr_name = None
    # GARAGE, not DOOR. Home Assistant's HomeKit bridge only maps a cover to a
    # HomeKit Door when it also supports SET_POSITION, which this door cannot
    # (it reports open/closed with no position). device_class DOOR therefore
    # fell through to WindowCoveringBasic and showed up in HomeKit as blinds.
    # GARAGE maps to GarageDoorOpener on OPEN|CLOSE alone, which is the honest
    # match: a binary barrier with opening/closing transitions and no
    # intermediate position.
    _attr_device_class = CoverDeviceClass.GARAGE
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "door")
        # The door reports open/closed only -- never a position, and never
        # "moving". Travel direction is inferred from the command we sent
        # and expires so a stuck door cannot show as moving forever.
        self._moving: str | None = None
        self._cancel_expiry: Any = None
        self._cancel_refresh: Any = None

    @property
    def is_closed(self) -> bool | None:
        if (opened := self.coordinator.data.opened) is None:
            return None
        return not opened

    @property
    def is_opening(self) -> bool:
        return self._moving == "opening"

    @property
    def is_closing(self) -> bool:
        return self._moving == "closing"

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_move(protocol.open_door(), "opening")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_move(protocol.close_door(), "closing")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        self._clear_motion()
        await self.coordinator.async_send(protocol.pause_door())

    async def _async_move(self, frame: bytes, direction: str) -> None:
        self._set_motion(direction)
        try:
            await self.coordinator.async_send(frame)
        except Exception:
            self._clear_motion()
            self.async_write_ha_state()
            raise
        # The status frame that comes back is captured before travel
        # finishes, so schedule a second look once it should have arrived.
        self._cancel_pending_refresh()
        self._cancel_refresh = async_call_later(
            self.hass, POST_COMMAND_REFRESH, self._async_confirm
        )

    @callback
    def _set_motion(self, direction: str) -> None:
        self._clear_motion()
        self._moving = direction
        self._cancel_expiry = async_call_later(
            self.hass, MOTION_TIMEOUT, self._async_expire_motion
        )
        self.async_write_ha_state()

    @callback
    def _clear_motion(self) -> None:
        self._moving = None
        if self._cancel_expiry is not None:
            self._cancel_expiry()
            self._cancel_expiry = None

    @callback
    def _async_expire_motion(self, _now: Any) -> None:
        self._cancel_expiry = None
        self._moving = None
        self.async_write_ha_state()

    @callback
    def _cancel_pending_refresh(self) -> None:
        if self._cancel_refresh is not None:
            self._cancel_refresh()
            self._cancel_refresh = None

    async def _async_confirm(self, _now: Any) -> None:
        self._cancel_refresh = None
        self._clear_motion()
        # Push the cleared motion now; if the refresh below fails, the entity
        # must still stop claiming the door is moving.
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_will_remove_from_hass(self) -> None:
        self._clear_motion()
        self._cancel_pending_refresh()
        await super().async_will_remove_from_hass()
