"""Base entity for the Nokia FastMile 4G integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FastMileCoordinator


class FastMileEntity(CoordinatorEntity[FastMileCoordinator]):
    """Entity attached to the receiver device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FastMileCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        status = coordinator.data
        identifier = entry.unique_id or entry.entry_id

        self._attr_unique_id = f"{identifier}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(status.mac))} if status.mac else set(),
            # Entity ids derive from this name: sensor.fastmile_rsrp, button.fastmile_reboot, ...
            name="FastMile",
            manufacturer="Nokia",
            model=status.model,
            sw_version=status.sw_version,
            serial_number=status.serial_number,
            configuration_url=f"https://{entry.data[CONF_HOST]}/",
        )
