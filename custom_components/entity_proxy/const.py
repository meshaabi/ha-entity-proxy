"""Constants for Entity Proxy."""

from homeassistant.const import Platform

DOMAIN = "entity_proxy"
PLATFORMS = (Platform.SWITCH, Platform.LIGHT, Platform.CLIMATE)
CONF_PREFERRED = "preferred"
CONF_FALLBACK = "fallback"
CONF_PLATFORM = "platform"
CONF_CAPABILITIES = "capabilities"
