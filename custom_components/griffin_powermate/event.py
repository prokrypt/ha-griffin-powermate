from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTIONS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([KnobEvent(entry.runtime_data)])


class KnobEvent(EventEntity):
    _attr_has_entity_name = True
    _attr_name = "Knob"
    _attr_event_types = list(ACTIONS.values())

    def __init__(self, pm) -> None:
        self._pm = pm
        self._attr_unique_id = f"{pm.address}_knob"
        self._attr_device_info = pm.device_info

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{self._pm.signal}_action", self._on_action))

    @callback
    def _on_action(self, action: str) -> None:
        self._trigger_event(action)
        self.async_write_ha_state()
