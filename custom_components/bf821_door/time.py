"""Time platform for the BF821 coop door's schedules."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import BF821ConfigEntry, BF821Coordinator
from .entity import BF821Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BF821ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the schedule times."""
    coordinator = entry.runtime_data
    async_add_entities(
        [BF821OpenTime(coordinator), BF821CloseTime(coordinator)]
    )


class BF821OpenTime(BF821Entity, TimeEntity):
    """When the door opens on a schedule."""

    _attr_translation_key = "open_time"

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "open_time")

    @property
    def native_value(self) -> time | None:
        return self.coordinator.data.open_timer

    async def async_set_value(self, value: time) -> None:
        # The enable flag travels in the same frame; preserve it rather than
        # silently switching the schedule on.
        enabled = bool(self.coordinator.data.open_timer_on)
        await self.coordinator.async_send(protocol.set_open_timer(enabled, value))


class BF821CloseTime(BF821Entity, TimeEntity):
    """When the door closes on a schedule."""

    _attr_translation_key = "close_time"

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "close_time")

    @property
    def native_value(self) -> time | None:
        return self.coordinator.data.close_timer

    async def async_set_value(self, value: time) -> None:
        enabled = bool(self.coordinator.data.close_timer_on)
        await self.coordinator.async_send(protocol.set_close_timer(enabled, value))
