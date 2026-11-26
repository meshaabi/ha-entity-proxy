# Entity Proxy

Give a switch, light, or thermostat one Home Assistant entity backed by two
existing controls. The proxy follows the preferred entity while it reports
available. It automatically follows the fallback when the preferred entity
becomes unavailable and returns when it recovers.

Pair two entities that control the same physical device. The sources can
come from any Home Assistant integration. For example, select a LAN-controlled
light as preferred and the same bulb's cloud-controlled light as fallback.

## Install

Minimum Home Assistant version: 2026.11.3. The initial release was tested on that version.

1. In **Settings → Marketplace**, choose **Add from link**.
2. Enter `https://github.com/meshaabi/ha-entity-proxy` and add it as an integration.
3. Install **Entity Proxy**, then choose its name and two sources in the setup
   form. Both sources need to be available during initial setup so the proxy
   can read their capabilities.

For a manual install, copy `custom_components/entity_proxy` to the
`custom_components` directory in your Home Assistant configuration. Restart
Home Assistant and add **Entity Proxy** under **Settings → Devices & services**.

## Supported controls

| Domain | Controls |
| --- | --- |
| Switch | On and off |
| Light | On and off, shared brightness, colour, colour temperature and transitions |
| Climate | Shared HVAC modes, power controls and target temperature or range where both sources support them |

The proxy uses the shared capabilities detected at setup. Reconfigure it if
the capabilities or sources change. The `active_entity_id` state attribute
shows the current route. The two source entities keep their identities.

Each action goes to one source based on Home Assistant’s reported state and
availability. The selected source returns any service error to the caller.
An action may succeed at the integration level before the physical device
responds. Reconnecting a source changes the route for future commands.

## Tests

Run on Python 3.14 in an isolated virtual environment.

```sh
python -m pip install 'homeassistant==2026.11.3'
python -m unittest discover -s tests -v
```
