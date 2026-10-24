import asyncio
import contextlib
import logging
import time

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ACTIONS,
    BATTERY_INTERVAL,
    DOMAIN,
    EVENT,
    LED_OFF,
    PRESS_TURN,
    TURN_GAP,
    TURN_MAX_WAIT,
    TURNS,
    UUID_BATTERY,
    UUID_LED,
    UUID_READ,
    is_duplicate,
    is_press_turn_tail,
)
from .turns import TurnGrouper

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.EVENT, Platform.LIGHT, Platform.SENSOR]
POLL_INTERVAL = 1  # seconds between checks for a fresh advertisement


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
        self._battery_warned = False
        self._last = (None, 0.0)
        self._press_turn = float("-inf")
        self._turns = TurnGrouper(hass.loop, TURN_GAP, TURN_MAX_WAIT, self._fire)

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
        if code in TURNS:
            self._turns.add(ACTIONS[code])
            return
        self._turns.flush()  # keep pending turns ahead of the button event
        self._fire(ACTIONS.get(code) or f"0x{code:02x}", 1)

    def _fire(self, action: str, steps: int) -> None:
        self.hass.bus.async_fire(EVENT, {"address": self.address, "action": action, "steps": steps})
        if action in ACTIONS.values():
            async_dispatcher_send(self.hass, f"{self.signal}_action", action, steps)

    def _set_battery(self, level: int) -> None:
        self.battery = level
        async_dispatcher_send(self.hass, f"{self.signal}_update")

    def _on_battery(self, _char, data: bytearray) -> None:
        if data:
            self._set_battery(data[0])

    async def _refresh_battery(self, resubscribe: bool) -> None:
        # the level can't be read; the knob sends it once per subscribe, so re-subscribe to refresh (as powuhmate did)
        try:
            if resubscribe:
                await self.client.stop_notify(UUID_BATTERY)
            await self.client.start_notify(UUID_BATTERY, self._on_battery)
        except BleakError as err:
            if self._battery_warned:
                _LOGGER.debug("PowerMate %s battery notifications failed: %s", self.address, err)
            else:
                self._battery_warned = True
                _LOGGER.warning("PowerMate %s: battery level unavailable: %s", self.address, err)

    async def run(self) -> None:
        # an idle knob advertises in short bursts minutes apart, so only try to connect right after hearing one.
        # HA skips advertisement callbacks when the data is the same as last time, and the knob's never changes,
        # so poll the time HA last heard it instead
        heard = 0.0
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            info = bluetooth.async_last_service_info(self.hass, self.address, connectable=True)
            if info and info.time > heard:
                heard = info.time
                gone = asyncio.Event()
                client = None
                try:
                    client = await establish_connection(
                        BleakClientWithServiceCache, info.device, self.address, disconnected_callback=lambda _: gone.set()
                    )
                    await client.start_notify(UUID_READ, self._on_notify)
                    self.client = client
                    await self.set_led(self.led)  # knob forgets its LED across reconnects
                    _LOGGER.info("PowerMate %s connected", self.address)
                    resubscribe = False
                    while not gone.is_set():
                        await self._refresh_battery(resubscribe)
                        resubscribe = True
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(gone.wait(), BATTERY_INTERVAL)
                    _LOGGER.info("PowerMate %s disconnected", self.address)
                except (BleakError, asyncio.TimeoutError) as err:
                    _LOGGER.debug("PowerMate %s: %s", self.address, err)
                except Exception:  # keep the loop alive, or the knob never reconnects
                    _LOGGER.exception("PowerMate %s: unexpected error", self.address)
                finally:
                    self.client = None
                    if client and client.is_connected:
                        with contextlib.suppress(BleakError, asyncio.TimeoutError):
                            await client.disconnect()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry.runtime_data = pm = PowerMate(hass, entry.data[CONF_ADDRESS], entry.title)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_create_background_task(hass, pm.run(), DOMAIN)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # background task is cancelled by HA on unload
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
