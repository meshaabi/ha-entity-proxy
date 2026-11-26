"""Test the integration on Home Assistant Core using synthetic devices."""

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from homeassistant import loader
from homeassistant.bootstrap import async_from_config_dict
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import DATA_COMPONENT as CLIMATE_COMPONENT
from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.components.light.const import DATA_COMPONENT as LIGHT_COMPONENT
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.switch.const import DATA_COMPONENT as SWITCH_COMPONENT
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "entity_proxy"


class SyntheticDevice:
    _attr_should_poll = False
    _available = True

    def __init__(self, name):
        self._attr_name = name
        self._attr_unique_id = name
        self.calls = []

    @property
    def available(self):
        return self._available

    def report_available(self, available):
        self._available = available
        self.async_write_ha_state()


class SyntheticSwitch(SyntheticDevice, SwitchEntity):
    _attr_is_on = False
    fail = False

    async def async_turn_on(self, **kwargs):
        self.calls.append("on")
        if self.fail:
            raise HomeAssistantError("Synthetic delivery error")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self.calls.append("off")
        self._attr_is_on = False
        self.async_write_ha_state()


class SyntheticLight(SyntheticDevice, LightEntity):
    _attr_is_on = False
    _attr_brightness = 128
    _attr_color_temp_kelvin = 3000

    def __init__(self, name, modes, limits=(2700, 6500)):
        super().__init__(name)
        self._attr_supported_color_modes = set(modes)
        self._attr_color_mode = modes[0]
        self._attr_min_color_temp_kelvin, self._attr_max_color_temp_kelvin = limits

    async def async_turn_on(self, **kwargs):
        self.calls.append(kwargs)
        self._attr_is_on = True
        self._attr_brightness = kwargs.get("brightness", self._attr_brightness)
        if "color_temp_kelvin" in kwargs:
            self._attr_color_temp_kelvin = kwargs["color_temp_kelvin"]
            self._attr_color_mode = ColorMode.COLOR_TEMP
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self.calls.append(kwargs)
        self._attr_is_on = False
        self.async_write_ha_state()


class SyntheticClimate(SyntheticDevice, ClimateEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_mode = HVACMode.HEAT
    _attr_native_current_temperature = 20.0
    _attr_native_target_temperature = 21.0
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    def __init__(self, name, modes, limits):
        super().__init__(name)
        self._attr_hvac_modes = modes
        self._attr_min_temp, self._attr_max_temp = limits

    async def async_set_hvac_mode(self, hvac_mode):
        self._attr_hvac_mode = hvac_mode
        self.calls.append(hvac_mode)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs):
        self.calls.append(kwargs)
        self._attr_native_target_temperature = kwargs["temperature"]
        self.async_write_ha_state()


class TestProxyOnCore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.hass = HomeAssistant(tmp.name)
        self.hass.config.skip_pip = True
        loader.async_setup(self.hass)
        self.addAsyncCleanup(self.hass.async_stop)
        shutil.copytree(
            ROOT / "custom_components", Path(tmp.name) / "custom_components"
        )
        config = {
            "homeassistant": {
                "latitude": 0,
                "longitude": 0,
                "unit_system": "metric",
                "time_zone": "UTC",
            },
            "switch": {},
            "light": {},
            "climate": {},
        }
        self.assertIs(await async_from_config_dict(config, self.hass), self.hass)
        await self.hass.async_start()

    async def _start_flow(self, data, flow=None):
        manager = self.hass.config_entries.flow
        if flow is None:
            flow = await manager.async_init(DOMAIN, context={"source": "user"})
        result = await manager.async_configure(flow["flow_id"], data)
        await self.hass.async_block_till_done()
        return result

    async def _pair(self, name, preferred, fallback):
        result = await self._start_flow(
            {
                "name": name,
                "preferred": preferred.entity_id,
                "fallback": fallback.entity_id,
            }
        )
        self.assertEqual(result["type"], "create_entry", result)
        return result["result"]

    async def _add(self, component, *devices):
        await self.hass.data[component].async_add_entities(list(devices))
        await self.hass.async_block_till_done()

    def _state(self, entity_id):
        return self.hass.states.get(entity_id)

    async def _call(self, service, entity_id, **data):
        await self.hass.services.async_call(
            entity_id.split(".", 1)[0],
            service,
            {"entity_id": entity_id, **data},
            blocking=True,
        )
        await self.hass.async_block_till_done()

    async def test_switch_failover_recovery_and_unload(self):
        local, cloud = (
            SyntheticSwitch("Preferred switch"),
            SyntheticSwitch("Fallback switch"),
        )
        await self._add(SWITCH_COMPONENT, local, cloud)
        entry = await self._pair("Test switch", local, cloud)
        proxy = "switch.test_switch"

        await self._call("turn_on", proxy)
        self.assertEqual(local.calls, ["on"])
        self.assertFalse(cloud.calls)
        self.assertEqual(self._state(proxy).state, "on")

        local.report_available(False)
        await self.hass.async_block_till_done()
        self.assertEqual(
            self._state(proxy).attributes["active_entity_id"], cloud.entity_id
        )
        await self._call("turn_on", proxy)
        self.assertEqual(cloud.calls, ["on"])

        local.report_available(True)
        await self.hass.async_block_till_done()
        self.assertEqual(
            self._state(proxy).attributes["active_entity_id"], local.entity_id
        )
        await self._call("turn_off", proxy)
        self.assertEqual(local.calls, ["on", "off"])
        self.assertEqual(cloud.calls, ["on"])

        cloud.report_available(False)
        local.report_available(False)
        await self.hass.async_block_till_done()
        self.assertEqual(self._state(proxy).state, "unavailable")
        self.assertTrue(await self.hass.config_entries.async_unload(entry.entry_id))
        restored = self._state(proxy)
        local.report_available(True)
        await self.hass.async_block_till_done()
        self.assertIs(self._state(proxy), restored)
        local.report_available(False)
        cloud.report_available(True)
        self.assertTrue(await self.hass.config_entries.async_setup(entry.entry_id))
        await self.hass.async_block_till_done()
        self.assertEqual(
            self._state(proxy).attributes["active_entity_id"], cloud.entity_id
        )

    async def test_failed_dispatch_is_not_retried_and_registry_rename_works(self):
        local, cloud = (
            SyntheticSwitch("Preferred switch"),
            SyntheticSwitch("Fallback switch"),
        )
        await self._add(SWITCH_COMPONENT, local, cloud)
        await self._pair("Test switch", local, cloud)
        proxy = "switch.test_switch"
        local.fail = True
        with self.assertRaisesRegex(HomeAssistantError, "Synthetic delivery error"):
            await self._call("turn_on", proxy)
        self.assertFalse(cloud.calls)

        renamed = "switch.renamed_source"
        registry = er.async_get(self.hass)
        registry.async_update_entity(local.entity_id, new_entity_id=renamed)
        await self.hass.async_block_till_done()
        self.assertEqual(self._state(proxy).attributes["active_entity_id"], renamed)

    async def test_light_uses_shared_controls_and_ranges(self):
        local = SyntheticLight("Preferred light", [ColorMode.COLOR_TEMP, ColorMode.RGB])
        cloud = SyntheticLight(
            "Fallback light", [ColorMode.COLOR_TEMP, ColorMode.HS], (3000, 5500)
        )
        await self._add(LIGHT_COMPONENT, local, cloud)
        await self._pair("Test light", local, cloud)
        proxy = "light.test_light"
        state = self._state(proxy)
        self.assertEqual(
            set(state.attributes["supported_color_modes"]), {"hs", "color_temp"}
        )
        self.assertEqual(state.attributes["min_color_temp_kelvin"], 3000)
        self.assertEqual(state.attributes["max_color_temp_kelvin"], 5500)

        await self._call("turn_on", proxy, brightness=160, color_temp_kelvin=3500)
        self.assertEqual(local.calls[-1]["brightness"], 160)
        self.assertEqual(local.calls[-1]["color_temp_kelvin"], 3500)
        self.assertFalse(cloud.calls)
        self.assertEqual(self._state(proxy).attributes["brightness"], 160)

        local.report_available(False)
        await self._call("turn_on", proxy, hs_color=[120, 100])
        self.assertEqual(cloud.calls[-1]["hs_color"], (120.0, 100.0))

    async def test_thermostat_uses_shared_modes_and_target_limits(self):
        local = SyntheticClimate(
            "Preferred thermostat", [HVACMode.OFF, HVACMode.HEAT], (8, 30)
        )
        cloud = SyntheticClimate(
            "Fallback thermostat",
            [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL],
            (10, 25),
        )
        await self._add(CLIMATE_COMPONENT, local, cloud)
        await self._pair("Test thermostat", local, cloud)
        proxy = "climate.test_thermostat"
        state = self._state(proxy)
        self.assertEqual(set(state.attributes["hvac_modes"]), {"off", "heat"})
        self.assertEqual(state.attributes["min_temp"], 10)
        self.assertEqual(state.attributes["max_temp"], 25)

        await self._call("set_temperature", proxy, temperature=22)
        self.assertEqual([call["temperature"] for call in local.calls], [22.0])
        self.assertFalse(cloud.calls)
        local.report_available(False)
        await self._call("set_temperature", proxy, temperature=23)
        self.assertEqual([call["temperature"] for call in cloud.calls], [23.0])
        self.assertEqual(self._state(proxy).attributes["temperature"], 23)

    async def test_rejects_duplicate_pairs_and_proxy_sources(self):
        local, cloud = (
            SyntheticSwitch("Preferred switch"),
            SyntheticSwitch("Fallback switch"),
        )
        await self._add(SWITCH_COMPONENT, local, cloud)
        await self._pair("Test switch", local, cloud)

        duplicate = await self._start_flow(
            {
                "name": "Duplicate",
                "preferred": cloud.entity_id,
                "fallback": local.entity_id,
            }
        )
        self.assertEqual(duplicate["errors"], {"base": "already_configured"})
        recursive = await self._start_flow(
            {
                "name": "Recursive",
                "preferred": "switch.test_switch",
                "fallback": cloud.entity_id,
            }
        )
        self.assertEqual(recursive["errors"], {"base": "proxy_source"})

    async def test_reconfigure_preserves_proxy_identity(self):
        preferred = SyntheticSwitch("Preferred switch")
        fallback = SyntheticSwitch("Fallback switch")
        replacement = SyntheticSwitch("Replacement switch")
        await self._add(SWITCH_COMPONENT, preferred, fallback, replacement)
        entry = await self._pair("Test switch", preferred, fallback)
        proxy = "switch.test_switch"
        registry = er.async_get(self.hass)
        original_id = registry.async_get(proxy).id
        flow = await self.hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
        )
        result = await self._start_flow(
            {"preferred": replacement.entity_id, "fallback": fallback.entity_id}, flow
        )
        self.assertEqual(result["reason"], "reconfigure_successful")
        self.assertEqual(registry.async_get(proxy).id, original_id)
        await self._call("turn_on", proxy)
        self.assertEqual(replacement.calls, ["on"])
        self.assertFalse(preferred.calls)
        self.assertFalse(fallback.calls)
