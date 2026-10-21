from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    EFFECT_OFF,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import EFFECTS, led_byte


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([KnobLight(entry.runtime_data)])


class KnobLight(LightEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "LED"
    _attr_translation_key = "led"
    _attr_assumed_state = True  # knob can't report its LED
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = [EFFECT_OFF, *EFFECTS]

    def __init__(self, pm) -> None:
        self._pm = pm
        self._attr_unique_id = f"{pm.address}_led"
        self._attr_device_info = pm.device_info
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_effect = EFFECT_OFF

    async def async_added_to_hass(self) -> None:
        if last := await self.async_get_last_state():
            self._attr_is_on = last.state == STATE_ON
            self._attr_brightness = last.attributes.get(ATTR_BRIGHTNESS) or 255
            self._attr_effect = last.attributes.get(ATTR_EFFECT) or EFFECT_OFF
        await self._apply()

    async def async_turn_on(self, **kwargs) -> None:
        self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            self._attr_effect = EFFECT_OFF
        if ATTR_EFFECT in kwargs:
            self._attr_effect = kwargs[ATTR_EFFECT]
        await self._apply()

    async def async_turn_off(self, **kwargs) -> None:
        self._attr_is_on = False
        await self._apply()

    async def _apply(self) -> None:
        await self._pm.set_led(led_byte(self._attr_is_on, self._attr_brightness, self._attr_effect))
        self.async_write_ha_state()
