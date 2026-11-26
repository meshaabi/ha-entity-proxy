"""Configure a pair of entities that control the same device."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN, Platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .capabilities import climate_capabilities, light_capabilities
from .const import (
    CONF_CAPABILITIES,
    CONF_FALLBACK,
    CONF_PLATFORM,
    CONF_PREFERRED,
    DOMAIN,
    PLATFORMS,
)


class EntityProxyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Choose the preferred and fallback controls."""

    async def async_step_user(self, user_input=None):
        """Create a proxy."""
        return await self._async_pair("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        """Change the sources without replacing the proxy entity."""
        return await self._async_pair(
            "reconfigure", user_input, self._get_reconfigure_entry()
        )

    async def _async_pair(self, step, user_input, entry=None):
        errors = {}
        registry = er.async_get(self.hass)
        if user_input is not None:
            preferred = er.async_resolve_entity_id(registry, user_input[CONF_PREFERRED])
            fallback = er.async_resolve_entity_id(registry, user_input[CONF_FALLBACK])
            data, error = self._pair_data(registry, preferred, fallback, entry)
            if error:
                errors["base"] = error
            else:
                if entry:
                    return self.async_update_reload_and_abort(entry, data=data)
                return self.async_create_entry(title=user_input[CONF_NAME], data=data)

        domains = [entry.data[CONF_PLATFORM]] if entry else list(PLATFORMS)
        source_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(filter={"domain": domains})
        )
        fields = {
            vol.Required(CONF_PREFERRED): source_selector,
            vol.Required(CONF_FALLBACK): source_selector,
        }
        if not entry:
            fields = {vol.Required(CONF_NAME): selector.TextSelector(), **fields}
        schema = vol.Schema(fields)
        if entry:
            schema = self.add_suggested_values_to_schema(
                schema,
                {
                    field: er.async_resolve_entity_id(registry, entry.data[field])
                    for field in (CONF_PREFERRED, CONF_FALLBACK)
                },
            )
        return self.async_show_form(step_id=step, data_schema=schema, errors=errors)

    def _pair_data(self, registry, preferred, fallback, entry):
        if preferred is None or fallback is None:
            return None, "missing_source"
        if preferred == fallback:
            return None, "same_source"
        platform = preferred.split(".", 1)[0]
        if (
            platform not in PLATFORMS
            or fallback.split(".", 1)[0] != platform
            or (entry and platform != entry.data[CONF_PLATFORM])
        ):
            return None, "different_domains"
        references = []
        for entity_id in (preferred, fallback):
            registered = registry.async_get(entity_id)
            if registered and registered.platform == DOMAIN:
                return None, "proxy_source"
            references.append(registered.id if registered else entity_id)
        for existing in self._async_current_entries():
            if entry and existing.entry_id == entry.entry_id:
                continue
            if set(references) == {
                existing.data[CONF_PREFERRED],
                existing.data[CONF_FALLBACK],
            }:
                return None, "already_configured"

        primary_state = self.hass.states.get(preferred)
        backup_state = self.hass.states.get(fallback)
        if any(
            state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
            for state in (primary_state, backup_state)
        ):
            return None, "missing_source"

        capabilities = {}
        if platform == Platform.LIGHT:
            capabilities = light_capabilities(
                primary_state.attributes, backup_state.attributes
            )
        if platform == Platform.CLIMATE:
            capabilities = climate_capabilities(
                primary_state.attributes,
                backup_state.attributes,
                self.hass.config.units.temperature_unit,
            )
            if capabilities is None:
                return None, "no_common_modes"
        return {
            CONF_PREFERRED: references[0],
            CONF_FALLBACK: references[1],
            CONF_PLATFORM: platform,
            CONF_CAPABILITIES: capabilities,
        }, None
