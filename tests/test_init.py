"""Discovery through HA's Bluetooth stack, and the connection to a knob."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from bleak.exc import BleakError
from homeassistant.components.bluetooth import async_get_advertisement_callback
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.griffin_powermate.const import DOMAIN, EVENT, UUID_LED, UUID_READ

from .conftest import ADDRESS, service_info

pytestmark = pytest.mark.usefixtures("mock_bluetooth")

CONNECT = "custom_components.griffin_powermate.establish_connection"


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
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=bytearray([87]))
    client.disconnect = AsyncMock()
    return client


async def advertise(hass: HomeAssistant, **kwargs) -> None:
    async_get_advertisement_callback(hass)(service_info(**kwargs))
    await hass.async_block_till_done()


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
        connect.assert_not_called()  # HA has not heard the knob yet

        await advertise(hass)
        connect.assert_awaited_once()
        assert connect.await_args.args[2] == ADDRESS
        client.start_notify.assert_awaited_once()
        assert client.start_notify.await_args.args[0] == UUID_READ
        client.write_gatt_char.assert_awaited_once_with(UUID_LED, bytes([0x80]), response=True)
        battery = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{ADDRESS}_battery")
        assert hass.states.get(battery).state == "87"

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_led_write_error_keeps_the_connection(hass: HomeAssistant, entry, client) -> None:
    client.write_gatt_char.side_effect = BleakError("write rejected")
    with patch(CONNECT, AsyncMock(return_value=client)):
        await setup(hass, entry)
        await advertise(hass)
        client.read_gatt_char.assert_awaited_once()  # got past the LED write
        client.disconnect.assert_not_called()

        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_knob_actions_fire_events(hass: HomeAssistant, entry, client) -> None:
    events = async_capture_events(hass, EVENT)
    with patch(CONNECT, AsyncMock(return_value=client)):
        await setup(hass, entry)
        await advertise(hass)
        notify = client.start_notify.await_args.args[1]
        notify(None, bytearray())  # empty notification is ignored
        notify(None, bytearray([0x68]))
        await hass.async_block_till_done()

        assert [e.data for e in events] == [{"address": ADDRESS, "action": "cw"}]
        assert await hass.config_entries.async_unload(entry.entry_id)
