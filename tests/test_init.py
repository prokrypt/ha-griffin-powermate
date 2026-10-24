"""Discovery through HA's Bluetooth stack, and the connection to a knob."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from homeassistant.components.bluetooth import async_get_advertisement_callback
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    mock_restore_cache_with_extra_data,
)

from custom_components.griffin_powermate.const import DOMAIN, EVENT, UUID_BATTERY, UUID_LED, UUID_READ

from .conftest import ADDRESS, service_info

pytestmark = pytest.mark.usefixtures("mock_bluetooth")

CONNECT = "custom_components.griffin_powermate.establish_connection"


@pytest.fixture(autouse=True)
def fast_poll():
    with patch("custom_components.griffin_powermate.POLL_INTERVAL", 0.01, create=True):
        yield


async def settle() -> None:
    """Let the connection loop run a few rounds."""
    await asyncio.sleep(0.1)


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=ADDRESS, title=f"PowerMate Bluetooth {ADDRESS}", data={CONF_ADDRESS: ADDRESS}
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def client() -> MagicMock:
    client = MagicMock(is_connected=True)
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    client.disconnect = AsyncMock()
    return client


async def advertise(hass: HomeAssistant, **kwargs) -> None:
    async_get_advertisement_callback(hass)(service_info(**kwargs))
    await hass.async_block_till_done()


def notified(client: MagicMock, uuid: str):
    """The callback the integration subscribed to `uuid` with."""
    [callback] = [c.args[1] for c in client.start_notify.await_args_list if c.args[0] == uuid]
    return callback


def battery_state(hass: HomeAssistant) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_battery")
    return hass.states.get(entity_id).state


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await async_setup_component(hass, "bluetooth", {})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("name", ["PowerMate Bluetooth", None])
async def test_advert_starts_discovery_with_or_without_name(hass: HomeAssistant, name) -> None:
    assert await async_setup_component(hass, "bluetooth", {})
    with patch("homeassistant.components.bluetooth.manager.discovery_flow.async_create_flow") as create_flow:
        await advertise(hass, name=name)
    assert [(c.args[1], c.args[3].address) for c in create_flow.call_args_list] == [(DOMAIN, ADDRESS)]


async def test_connects_when_the_knob_advertises(hass: HomeAssistant, entry, client) -> None:
    with patch(CONNECT, AsyncMock(return_value=client)) as connect:
        await setup(hass, entry)
        await settle()
        connect.assert_not_called()  # HA has not heard the knob yet

        await advertise(hass)
        await settle()
        connect.assert_awaited_once()
        assert connect.await_args.args[2] == ADDRESS
        assert [c.args[0] for c in client.start_notify.await_args_list] == [UUID_READ, UUID_BATTERY]
        client.write_gatt_char.assert_awaited_once_with(UUID_LED, bytes([0x80]), response=True)
        notified(client, UUID_BATTERY)(None, bytearray([87]))
        await hass.async_block_till_done()
        assert battery_state(hass) == "87"

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_led_write_error_keeps_the_connection(hass: HomeAssistant, entry, client) -> None:
    client.write_gatt_char.side_effect = BleakError("write rejected")
    with patch(CONNECT, AsyncMock(return_value=client)):
        await setup(hass, entry)
        await advertise(hass)
        await settle()
        notified(client, UUID_BATTERY)  # got past the LED write
        client.disconnect.assert_not_called()

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_knob_actions_fire_events(hass: HomeAssistant, entry, client) -> None:
    events = async_capture_events(hass, EVENT)
    with patch(CONNECT, AsyncMock(return_value=client)):
        await setup(hass, entry)
        await advertise(hass)
        await settle()
        notify = notified(client, UUID_READ)
        notify(None, bytearray())  # empty notification is ignored
        notify(None, bytearray([0x68]))
        await hass.async_block_till_done()

        assert [e.data for e in events] == [{"address": ADDRESS, "action": "cw", "steps": 1}]
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_reconnects_when_the_knob_advertises_the_same_data_again(hass: HomeAssistant, entry, client) -> None:
    """HA skips callbacks for an advert identical to the last one; the knob's never change."""
    with patch(CONNECT, AsyncMock(return_value=client)) as connect:
        await setup(hass, entry)
        await advertise(hass)
        await settle()
        assert connect.await_count == 1

        client.is_connected = False
        connect.await_args.kwargs["disconnected_callback"](client)
        await settle()
        assert connect.await_count == 1  # not heard since

        await advertise(hass)  # same data as before
        await settle()
        assert connect.await_count == 2

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unexpected_error_does_not_stop_reconnecting(hass: HomeAssistant, entry, client) -> None:
    with patch(CONNECT, AsyncMock(side_effect=[RuntimeError("boom"), client])) as connect:
        await setup(hass, entry)
        await advertise(hass)
        await settle()
        await advertise(hass)
        await settle()
        assert connect.await_count == 2
        assert client.start_notify.await_count == 2  # knob events + battery, once

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_battery_is_refreshed_by_resubscribing(hass: HomeAssistant, entry, client) -> None:
    """The level is notify-only and the knob sends it once per subscribe (powuhmate re-subscribed every 600s)."""
    with (
        patch("custom_components.griffin_powermate.BATTERY_INTERVAL", 0.03),
        patch(CONNECT, AsyncMock(return_value=client)),
    ):
        await setup(hass, entry)
        await advertise(hass)
        await settle()
        client.read_gatt_char.assert_not_called()
        battery_subscribes = [c for c in client.start_notify.await_args_list if c.args[0] == UUID_BATTERY]
        assert len(battery_subscribes) >= 2
        client.stop_notify.assert_awaited_with(UUID_BATTERY)

        battery_subscribes[-1].args[1](None, bytearray([64]))
        await hass.async_block_till_done()
        assert battery_state(hass) == "64"

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_battery_failure_is_logged_once(hass: HomeAssistant, entry, client, caplog) -> None:
    client.start_notify.side_effect = lambda uuid, _cb: _raise(BleakError("not found")) if uuid == UUID_BATTERY else None
    with (
        patch("custom_components.griffin_powermate.BATTERY_INTERVAL", 0.03),
        patch(CONNECT, AsyncMock(return_value=client)) as connect,
    ):
        await setup(hass, entry)
        await advertise(hass)
        await settle()
        client.is_connected = False
        connect.await_args.kwargs["disconnected_callback"](client)
        await advertise(hass)
        await settle()
        assert connect.await_count == 2
        assert caplog.text.count("battery level unavailable") == 1

        assert await hass.config_entries.async_unload(entry.entry_id)


def _raise(err: Exception):
    raise err


async def test_battery_restored_until_the_knob_reports(hass: HomeAssistant, entry, client) -> None:
    entity_id = f"sensor.powermate_bluetooth_{ADDRESS.lower().replace(':', '_')}_battery"
    mock_restore_cache_with_extra_data(
        hass, [(State(entity_id, "55"), {"native_value": 55, "native_unit_of_measurement": "%"})]
    )
    with patch(CONNECT, AsyncMock(return_value=client)):
        await setup(hass, entry)
        assert battery_state(hass) == "55"

        await advertise(hass)
        await settle()
        assert battery_state(hass) == "55"  # until the knob sends its level
        notified(client, UUID_BATTERY)(None, bytearray([87]))
        await hass.async_block_till_done()
        assert battery_state(hass) == "87"

        assert await hass.config_entries.async_unload(entry.entry_id)
