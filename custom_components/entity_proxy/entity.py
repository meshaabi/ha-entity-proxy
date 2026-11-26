"""State selection and service forwarding shared by proxy entities."""

import asyncio
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_FALLBACK, CONF_PLATFORM, CONF_PREFERRED, DOMAIN


class ProxyEntity(Entity):
    """Use the first available source and forward each command to one entity."""

    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.title
        self._platform = entry.data[CONF_PLATFORM]
        self._references = (entry.data[CONF_PREFERRED], entry.data[CONF_FALLBACK])
        self._sources: tuple[str, ...] = ()
        self._unsubscribe = None
        self._command_lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        """Return whether either source has a usable state."""
        return self.active_state is not None

    @property
    def active_state(self) -> State | None:
        """Return the preferred state or the fallback state."""
        for entity_id in self._sources:
            state = self.hass.states.get(entity_id)
            if state is not None and state.state not in (
                STATE_UNAVAILABLE,
                STATE_UNKNOWN,
            ):
                return state
        return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Expose the route currently used for state and new commands."""
        state = self.active_state
        return {"active_entity_id": state.entity_id} if state else {}

    def source_attribute(self, key: str) -> Any:
        """Read an attribute on the active source."""
        state = self.active_state
        return state.attributes.get(key) if state else None

    async def async_added_to_hass(self) -> None:
        """Track both sources, including registered entity renames."""
        await super().async_added_to_hass()
        self._bind_sources()
        self.async_on_remove(self._remove_sources)
        self.async_on_remove(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed
            )
        )

    @callback
    def _remove_sources(self) -> None:
        self._unbind_sources()
        self._sources = ()

    @callback
    def _unbind_sources(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _bind_sources(self) -> bool:
        registry = er.async_get(self.hass)
        sources = []
        for reference in self._references:
            entity_id = er.async_resolve_entity_id(registry, reference)
            if entity_id is None:
                continue
            registered = registry.async_get(entity_id)
            if entity_id != self.entity_id and (
                registered is None or registered.platform != DOMAIN
            ):
                sources.append(entity_id)
        if self._sources == tuple(sources):
            return False
        self._unbind_sources()
        self._sources = tuple(sources)
        self._unsubscribe = async_track_state_change_event(
            self.hass, self._sources, self._source_changed
        )
        return True

    @callback
    def _registry_changed(self, _event) -> None:
        if self._bind_sources():
            self.async_write_ha_state()

    @callback
    def _source_changed(self, _event) -> None:
        self.async_write_ha_state()

    async def async_forward(self, service: str, **data: Any) -> None:
        """Forward a standard action using the original request context."""
        async with self._command_lock:
            if (state := self.active_state) is None:
                raise ServiceValidationError("Both proxy sources are unavailable")
            await self.hass.services.async_call(
                self._platform,
                service,
                {**data, ATTR_ENTITY_ID: state.entity_id},
                blocking=True,
                context=self._context,
            )
