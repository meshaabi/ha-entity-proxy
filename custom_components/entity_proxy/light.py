"""Light entities for Entity Proxy."""

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    LightEntityFeature,
    color_supported,
)
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON, STATE_ON
from homeassistant.exceptions import ServiceValidationError

from .const import CONF_CAPABILITIES
from .entity import ProxyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Add the configured light."""
    async_add_entities([ProxyLight(entry)])


class ProxyLight(ProxyEntity, LightEntity):
    """Follow the active light using the common controls."""

    def __init__(self, entry):
        super().__init__(entry)
        capabilities = entry.data[CONF_CAPABILITIES]
        self._attr_supported_color_modes = {
            ColorMode(mode) for mode in capabilities["supported_color_modes"]
        }
        self._attr_supported_features = LightEntityFeature(
            capabilities["supported_features"]
        )
        if ColorMode.COLOR_TEMP in self._attr_supported_color_modes:
            self._attr_min_color_temp_kelvin = capabilities["min_color_temp_kelvin"]
            self._attr_max_color_temp_kelvin = capabilities["max_color_temp_kelvin"]

    @property
    def is_on(self) -> bool | None:
        """Return the active light's power state."""
        state = self.active_state
        return state.state == STATE_ON if state else None

    @property
    def color_mode(self) -> ColorMode:
        """Represent the active mode using a shared colour format."""
        modes = self._attr_supported_color_modes
        mode = self.source_attribute("color_mode")
        if ColorMode.ONOFF in modes:
            return ColorMode.ONOFF
        if ColorMode.BRIGHTNESS in modes:
            return ColorMode.BRIGHTNESS
        if mode in modes:
            return ColorMode(mode)
        if ColorMode.HS in modes and color_supported({mode}):
            return ColorMode.HS
        return ColorMode.UNKNOWN

    @property
    def brightness(self) -> int | None:
        """Return brightness reported by the active light."""
        return self.source_attribute("brightness")

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return colour in Home Assistant's HSV representation."""
        return self.source_attribute("hs_color")

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the active light's reported colour temperature."""
        return self.source_attribute("color_temp_kelvin")

    async def async_turn_on(self, **kwargs):
        """Forward a power-on command and its shared modifiers."""
        if (kelvin := kwargs.get("color_temp_kelvin")) is not None and (
            ColorMode.COLOR_TEMP not in self._attr_supported_color_modes
            or not self.min_color_temp_kelvin <= kelvin <= self.max_color_temp_kelvin
        ):
            raise ServiceValidationError(
                "Colour temperature is outside the shared range"
            )
        await self.async_forward(SERVICE_TURN_ON, **kwargs)

    async def async_turn_off(self, **kwargs):
        """Turn off the active source."""
        await self.async_forward(SERVICE_TURN_OFF, **kwargs)
