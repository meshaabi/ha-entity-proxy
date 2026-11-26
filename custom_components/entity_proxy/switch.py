"""Switch entities for Entity Proxy."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_ON

from .entity import ProxyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Add the configured switch."""
    async_add_entities([ProxySwitch(entry)])


class ProxySwitch(ProxyEntity, SwitchEntity):
    """Follow the active switch."""

    @property
    def is_on(self) -> bool | None:
        """Return the active switch's power state."""
        state = self.active_state
        return state.state == STATE_ON if state else None

    async def async_turn_on(self, **kwargs):
        """Turn on the active source."""
        await self.async_forward(SERVICE_TURN_ON)

    async def async_turn_off(self, **kwargs):
        """Turn off the active source."""
        await self.async_forward(SERVICE_TURN_OFF)
