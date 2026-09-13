"""Switch platform for the BF821 coop door."""

from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up the door's switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BF821LightModeSwitch(coordinator),
            BF821OpenTimerSwitch(coordinator),
            BF821CloseTimerSwitch(coordinator),
            BF821LampSwitch(coordinator),
        ]
    )


class BF821LightModeSwitch(BF821Entity, SwitchEntity):
    """Light mode: opens above ~300 lux, closes below ~100 lux."""

    _attr_translation_key = "light_mode"

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "light_mode")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.auto_by_light

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_send(protocol.set_auto_by_light(True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_send(protocol.set_auto_by_light(False))


class _BF821TimerSwitch(BF821Entity, SwitchEntity):
    """Enables one of the two scheduled movements.

    The door needs the time supplied alongside the enable flag, so toggling
    replays whatever time it last reported -- falling back to the vendor
    app's default if the RTC has been wiped.
    """

    _default = time(6, 0, 0)

    def _current_time(self) -> time | None:
        raise NotImplementedError

    def _build(self, on: bool, value: time) -> bytes:
        raise NotImplementedError

    async def _async_set(self, on: bool) -> None:
        value = self._current_time() or self._default
        await self.coordinator.async_send(self._build(on, value))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)


class BF821OpenTimerSwitch(_BF821TimerSwitch):
    """Scheduled opening."""

    _attr_translation_key = "open_timer"
    _default = time(6, 0, 0)

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "open_timer")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.open_timer_on

    def _current_time(self) -> time | None:
        return self.coordinator.data.open_timer

    def _build(self, on: bool, value: time) -> bytes:
        return protocol.set_open_timer(on, value)


class BF821CloseTimerSwitch(_BF821TimerSwitch):
    """Scheduled closing."""

    _attr_translation_key = "close_timer"
    _default = time(18, 0, 0)

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "close_timer")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.close_timer_on

    def _current_time(self) -> time | None:
        return self.coordinator.data.close_timer

    def _build(self, on: bool, value: time) -> bytes:
        return protocol.set_close_timer(on, value)


class BF821LampSwitch(BF821Entity, SwitchEntity):
    """The unit's lamp.

    The door never reports lamp state in any notification frame, so this is
    write-only and shown as an assumed state.
    """

    _attr_translation_key = "lamp"
    _attr_assumed_state = True

    def __init__(self, coordinator: BF821Coordinator) -> None:
        super().__init__(coordinator, "lamp")
        self._is_on = False

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_send(protocol.set_lamp(True))
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_send(protocol.set_lamp(False))
        self._is_on = False
        self.async_write_ha_state()
