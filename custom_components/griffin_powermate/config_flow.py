import re

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak, async_discovered_service_info
from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .const import DOMAIN, LOCAL_NAME, UUID_SERVICE

ADDRESS_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def is_powermate(info: BluetoothServiceInfoBleak) -> bool:
    # same rule as the manifest matchers; a knob heard without its name is named after its address
    return info.name == LOCAL_NAME or UUID_SERVICE in (u.lower() for u in info.service_uuids)


class GriffinPowermateConfigFlow(ConfigFlow, domain=DOMAIN):
    _address: str

    async def async_step_bluetooth(self, info: BluetoothServiceInfoBleak):
        await self.async_set_unique_id(info.address)
        self._abort_if_unique_id_configured()
        self._address = info.address
        self.context["title_placeholders"] = {"name": f"{LOCAL_NAME} {info.address}"}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title=f"{LOCAL_NAME} {self._address}", data={CONF_ADDRESS: self._address})
        self._set_confirm_only()
        return self.async_show_form(step_id="confirm", description_placeholders={"address": self._address})

    async def async_step_user(self, user_input=None):
        # pick a knob HA heard recently, or type the address of one it hasn't heard yet
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper().replace("-", ":")
            if ADDRESS_RE.match(address):
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"{LOCAL_NAME} {address}", data={CONF_ADDRESS: address})
            errors[CONF_ADDRESS] = "invalid_address"
        current = self._async_current_ids()
        found = sorted(
            {i.address for i in async_discovered_service_info(self.hass) if is_powermate(i) and i.address not in current}
        )
        options = SelectSelectorConfig(options=found, custom_value=True)
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required(CONF_ADDRESS): SelectSelector(options)}), errors=errors
        )
