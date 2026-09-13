"""The BF821 chicken coop door integration."""

from __future__ import annotations

from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .coordinator import BF821ConfigEntry, BF821Coordinator
from .device import BF821Device

PLATFORMS: list[Platform] = [Platform.COVER, Platform.SWITCH, Platform.TIME]


async def async_setup_entry(hass: HomeAssistant, entry: BF821ConfigEntry) -> bool:
    """Set up a door from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    device = BF821Device(hass, address, entry.title)
    coordinator = BF821Coordinator(hass, entry, device)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BF821ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: BF821ConfigEntry
) -> None:
    """Reload when the poll interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)
