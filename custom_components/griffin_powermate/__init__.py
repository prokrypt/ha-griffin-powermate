import asyncio
import contextlib
import logging
import time

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ACTIONS,
    BATTERY_INTERVAL,
    DOMAIN,
    EVENT,
    LED_OFF,
    PRESS_TURN,
    UUID_BATTERY,
    UUID_LED,
    UUID_READ,
    is_duplicate,
    is_press_turn_tail,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.EVENT, Platform.LIGHT, Platform.SENSOR]


class PowerMate:
    """Connection to one knob, shared by its entities."""

    def __init__(self, hass: HomeAssistant, address: str, title: str) -> None:
        self.hass = hass
        self.address = address
        self.signal = f"{DOMAIN}_{address}"
        self.device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, address)}, name=title, manufacturer="Griffin", model="PowerMate Bluetooth"
        )
        self.client = None
        self.led = LED_OFF
        self.battery = None
        self._last = (None, 0.0)
        self._press_turn = float("-inf")
        self._heard = asyncio.Event()

    async def set_led(self, value: int) -> None:
        self.led = value
        if self.client and self.client.is_connected:
            try:
                await self.client.write_gatt_char(UUID_LED, bytes([value]), response=True)
            except BleakError as err:
                _LOGGER.debug("PowerMate %s LED write failed: %s", self.address, err)

    def _on_notify(self, _char, data: bytearray) -> None:
        if not data:
            return
        code, now = data[0], time.monotonic()
        dup = is_duplicate(code, self._last[0], now - self._last[1]) or is_press_turn_tail(code, now - self._press_turn)
        self._last = (code, now)
        if code in PRESS_TURN:
            self._press_turn = now
        if dup:
            _LOGGER.debug("PowerMate %s: dropped 0x%02x", self.address, code)
            return
        action = ACTIONS.get(code)
        self.hass.bus.async_fire(EVENT, {"address": self.address, "action": action or f"0x{code:02x}"})
        if action:
            async_dispatcher_send(self.hass, f"{self.signal}_action", action)

    async def _read_battery(self) -> None:
        try:
            self.battery = (await self.client.read_gatt_char(UUID_BATTERY))[0]
        except BleakError as err:
            _LOGGER.debug("PowerMate %s battery read failed: %s", self.address, err)
            return
        async_dispatcher_send(self.hass, f"{self.signal}_update")

    @callback
    def on_advertisement(self, _info, _change) -> None:
        self._heard.set()

    async def run(self) -> None:
        # an idle knob advertises in short bursts minutes apart, so only try to connect right after hearing one
        while True:
            await self._heard.wait()
            self._heard.clear()
            device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
            if device:
                gone = asyncio.Event()
                client = None
                try:
                    client = await establish_connection(
                        BleakClientWithServiceCache, device, self.address, disconnected_callback=lambda _: gone.set()
                    )
                    await client.start_notify(UUID_READ, self._on_notify)
                    self.client = client
                    await self.set_led(self.led)  # knob forgets its LED across reconnects
                    _LOGGER.info("PowerMate %s connected", self.address)
                    while not gone.is_set():
                        await self._read_battery()
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(gone.wait(), BATTERY_INTERVAL)
                    _LOGGER.info("PowerMate %s disconnected", self.address)
                except (BleakError, asyncio.TimeoutError) as err:
                    _LOGGER.debug("PowerMate %s: %s", self.address, err)
                finally:
                    self.client = None
                    if client and client.is_connected:
                        await client.disconnect()
            await asyncio.sleep(1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry.runtime_data = pm = PowerMate(hass, entry.data[CONF_ADDRESS], entry.title)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            pm.on_advertisement,
            bluetooth.BluetoothCallbackMatcher(address=pm.address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )
    entry.async_create_background_task(hass, pm.run(), DOMAIN)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # background task is cancelled by HA on unload
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
