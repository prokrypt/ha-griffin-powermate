"""Shared fixtures and advertisement builders."""

from __future__ import annotations

from inspect import signature
import time

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
import pytest

from custom_components.griffin_powermate.const import LOCAL_NAME, UUID_SERVICE

ADDRESS = "00:12:92:08:2E:31"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load the integration from custom_components."""


# Bleak before 1.0 (HA 2025.3) requires an rssi; later versions deprecate passing one.
_BLE_DEVICE_EXTRA = {"rssi": -80} if "rssi" in signature(BLEDevice).parameters else {}


def service_info(
    *, address: str = ADDRESS, name: str | None = LOCAL_NAME, uuids: list[str] | None = None
) -> BluetoothServiceInfoBleak:
    """A PowerMate advertisement as HA's Bluetooth stack hands it over.

    name=None is a knob heard without its name: HA then reports the address as the name.
    """
    uuids = [UUID_SERVICE] if uuids is None else uuids
    adv = AdvertisementData(
        local_name=name,
        manufacturer_data={},
        service_data={},
        service_uuids=uuids,
        tx_power=None,
        rssi=-80,
        platform_data=(),
    )
    return BluetoothServiceInfoBleak(
        name=name or address,
        address=address,
        rssi=-80,
        manufacturer_data={},
        service_data={},
        service_uuids=uuids,
        source="local",
        device=BLEDevice(address, name, {}, **_BLE_DEVICE_EXTRA),
        advertisement=adv,
        connectable=True,
        time=time.monotonic(),
        tx_power=None,
    )
