"""Expose one Home Assistant control backed by two existing entities."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_PLATFORM


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the platform for the configured pair."""
    await hass.config_entries.async_forward_entry_setups(
        entry, [entry.data[CONF_PLATFORM]]
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the platform and state subscriptions."""
    return await hass.config_entries.async_unload_platforms(
        entry, [entry.data[CONF_PLATFORM]]
    )
