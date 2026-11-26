"""Negotiate a common set of controls from public Home Assistant state."""

from collections.abc import Mapping
from typing import Any

from homeassistant.components.climate import ClimateEntityFeature, HVACMode
from homeassistant.components.light import (
    ColorMode,
    LightEntityFeature,
    brightness_supported,
    color_supported,
    color_temp_supported,
)

CLIMATE_FEATURES = (
    ClimateEntityFeature.TARGET_TEMPERATURE
    | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


def light_capabilities(
    preferred: Mapping[str, Any], fallback: Mapping[str, Any]
) -> dict[str, Any]:
    """Use HSV as the shared colour representation that HA can translate."""
    primary_modes = set(preferred.get("supported_color_modes") or ())
    secondary_modes = set(fallback.get("supported_color_modes") or ())
    modes = []
    caps: dict[str, Any] = {}
    if color_supported(primary_modes) and color_supported(secondary_modes):
        modes.append(ColorMode.HS)
    if color_temp_supported(primary_modes) and color_temp_supported(secondary_modes):
        limits = _overlap(
            preferred, fallback, "min_color_temp_kelvin", "max_color_temp_kelvin"
        )
        if limits is not None:
            caps["min_color_temp_kelvin"], caps["max_color_temp_kelvin"] = limits
            modes.append(ColorMode.COLOR_TEMP)
    if not modes:
        modes.append(
            ColorMode.BRIGHTNESS
            if brightness_supported(primary_modes)
            and brightness_supported(secondary_modes)
            else ColorMode.ONOFF
        )
    caps["supported_color_modes"] = modes
    caps["supported_features"] = (
        preferred.get("supported_features", 0)
        & fallback.get("supported_features", 0)
        & LightEntityFeature.TRANSITION
    )
    return caps


def climate_capabilities(
    preferred: Mapping[str, Any], fallback: Mapping[str, Any], unit: str
) -> dict[str, Any] | None:
    """Find compatible modes and an overlapping target temperature range."""
    shared = set(preferred.get("hvac_modes") or ()) & set(
        fallback.get("hvac_modes") or ()
    )
    modes = [mode for mode in HVACMode if mode in shared]
    if not modes:
        return None
    features = (
        preferred.get("supported_features", 0)
        & fallback.get("supported_features", 0)
        & CLIMATE_FEATURES
    )
    caps: dict[str, Any] = {"hvac_modes": modes, "unit": unit}
    if (limits := _overlap(preferred, fallback, "min_temp", "max_temp")) is None:
        features &= ~(
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        )
    else:
        caps["min_temp"], caps["max_temp"] = limits
        if step := max(
            preferred.get("target_temp_step") or 0,
            fallback.get("target_temp_step") or 0,
        ):
            caps["target_temp_step"] = step
    caps["supported_features"] = features
    return caps


def _overlap(
    preferred: Mapping[str, Any], fallback: Mapping[str, Any], low: str, high: str
) -> tuple[float, float] | None:
    if any(
        value is None
        for value in (
            preferred.get(low),
            preferred.get(high),
            fallback.get(low),
            fallback.get(high),
        )
    ):
        return None
    minimum = max(preferred[low], fallback[low])
    maximum = min(preferred[high], fallback[high])
    return (minimum, maximum) if minimum <= maximum else None
