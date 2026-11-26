"""Thermostat entities for Entity Proxy."""

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.const import SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import CONF_CAPABILITIES
from .entity import ProxyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Add the configured thermostat."""
    async_add_entities([ProxyClimate(entry, hass.config.units.temperature_unit)])


class ProxyClimate(ProxyEntity, ClimateEntity):
    """Follow the active thermostat using shared modes and temperature limits."""

    def __init__(self, entry, unit):
        super().__init__(entry)
        capabilities = entry.data[CONF_CAPABILITIES]
        self._attr_native_temperature_unit = unit
        self._attr_hvac_modes = [HVACMode(mode) for mode in capabilities["hvac_modes"]]
        self._attr_supported_features = ClimateEntityFeature(
            capabilities["supported_features"]
        )
        if "min_temp" in capabilities:
            original_unit = capabilities["unit"]
            minimum = capabilities["min_temp"]
            self._attr_min_temp = TemperatureConverter.convert(
                minimum, original_unit, unit
            )
            self._attr_max_temp = TemperatureConverter.convert(
                capabilities["max_temp"], original_unit, unit
            )
            if step := capabilities.get("target_temp_step"):
                self._attr_target_temperature_step = round(
                    TemperatureConverter.convert(minimum + step, original_unit, unit)
                    - self._attr_min_temp,
                    3,
                )

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the active thermostat's mode."""
        state = self.active_state
        return HVACMode(state.state) if state and state.state in HVACMode else None

    @property
    def native_current_temperature(self) -> float | None:
        """Return the active source's current temperature in HA's unit."""
        return self.source_attribute("current_temperature")

    @property
    def native_target_temperature(self) -> float | None:
        """Return the active source's target."""
        return self.source_attribute("temperature")

    @property
    def native_target_temperature_low(self) -> float | None:
        """Return the lower target of the active source."""
        return self.source_attribute("target_temp_low")

    @property
    def native_target_temperature_high(self) -> float | None:
        """Return the higher target of the active source."""
        return self.source_attribute("target_temp_high")

    @property
    def hvac_action(self):
        """Return the active source's current heating or cooling activity."""
        return self.source_attribute("hvac_action")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set a shared mode on the active thermostat."""
        await self.async_forward(SERVICE_SET_HVAC_MODE, hvac_mode=hvac_mode)

    async def async_set_temperature(self, **kwargs):
        """Forward a shared target temperature or range."""
        await self.async_forward(SERVICE_SET_TEMPERATURE, **kwargs)

    async def async_turn_on(self) -> None:
        """Turn on the active thermostat."""
        await self.async_forward(SERVICE_TURN_ON)

    async def async_turn_off(self) -> None:
        """Turn off the active thermostat."""
        await self.async_forward(SERVICE_TURN_OFF)
