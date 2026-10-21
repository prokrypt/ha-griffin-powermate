"""Config flows: Bluetooth discovery and adding a knob by hand."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.loader import async_get_bluetooth
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.griffin_powermate.const import DOMAIN, UUID_SERVICE

from .conftest import ADDRESS, service_info

pytestmark = pytest.mark.usefixtures("mock_bluetooth")

OTHER_ADDRESS = "00:12:92:08:00:01"
TITLE = f"PowerMate Bluetooth {ADDRESS}"
COMPONENT = Path(__file__).parents[1] / "custom_components/griffin_powermate"


@pytest.fixture(autouse=True)
def no_setup():
    """The flows are tested on their own."""
    with patch("custom_components.griffin_powermate.async_setup_entry", return_value=True):
        yield


def discovered(*infos):
    return patch(
        "custom_components.griffin_powermate.config_flow.async_discovered_service_info",
        return_value=list(infos),
    )


async def test_manifest_matches_on_service_uuid(hass: HomeAssistant) -> None:
    """A knob heard without its name must still be discovered."""
    matchers = [m for m in await async_get_bluetooth(hass) if m["domain"] == DOMAIN]
    assert {"domain": DOMAIN, "service_uuid": UUID_SERVICE, "connectable": True} in matchers


@pytest.mark.parametrize("name", ["PowerMate Bluetooth", None])
async def test_bluetooth_discovery_creates_entry(hass: HomeAssistant, name) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info(name=name)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_lists_knobs_heard_with_or_without_name(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=OTHER_ADDRESS).add_to_hass(hass)
    with discovered(
        service_info(name=None),
        service_info(address=OTHER_ADDRESS),
        service_info(address="AA:BB:CC:DD:EE:FF", name="Something else", uuids=[]),
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    selector = result["data_schema"].schema[CONF_ADDRESS]
    assert selector.config["options"] == [ADDRESS]
    assert selector.config["custom_value"] is True


async def test_user_picks_a_heard_knob(hass: HomeAssistant) -> None:
    with discovered(service_info()):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    assert result["data"] == {CONF_ADDRESS: ADDRESS}


@pytest.mark.parametrize("typed", [ADDRESS, " 00:12:92:08:2e:31 ", "00-12-92-08-2E-31"])
async def test_user_types_an_address_ha_has_not_heard(hass: HomeAssistant, typed) -> None:
    with discovered():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: typed})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS}
    assert result["result"].unique_id == ADDRESS


async def test_user_rejects_a_bad_address(hass: HomeAssistant) -> None:
    with discovered():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: "00:12:92"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_ADDRESS: "invalid_address"}


async def test_user_typed_address_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS).add_to_hass(hass)
    with discovered():
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS.lower()})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_wins_over_a_pending_discovery(hass: HomeAssistant) -> None:
    await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info())
    with discovered(service_info()):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_ADDRESS: ADDRESS})
    assert result["type"] is FlowResultType.CREATE_ENTRY


def test_translations_match_strings() -> None:
    strings = json.loads((COMPONENT / "strings.json").read_text())
    assert json.loads((COMPONENT / "translations/en.json").read_text()) == strings
    assert "invalid_address" in strings["config"]["error"]
