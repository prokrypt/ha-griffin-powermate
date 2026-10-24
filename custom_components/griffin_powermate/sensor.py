from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([KnobBattery(entry.runtime_data)])


class KnobBattery(RestoreSensor):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_should_poll = False

    def __init__(self, pm) -> None:
        self._pm = pm
        self._attr_unique_id = f"{pm.address}_battery"
        self._attr_device_info = pm.device_info
        self._restored = None

    @property
    def native_value(self):
        # last known level until the knob reports one, e.g. after an HA restart
        return self._restored if self._pm.battery is None else self._pm.battery

    async def async_added_to_hass(self) -> None:
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._restored = last.native_value
        self.async_on_remove(async_dispatcher_connect(self.hass, f"{self._pm.signal}_update", self.async_write_ha_state))
