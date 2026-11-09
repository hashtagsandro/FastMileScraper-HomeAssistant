"""Binary sensors of the Nokia FastMile 4G integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FastMileConfigEntry, FastMileCoordinator
from .entity import FastMileEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FastMileConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities([FastMileLteConnected(entry.runtime_data)])


class FastMileLteConnected(FastMileEntity, BinarySensorEntity):
    """On while the receiver is attached to an LTE cell.

    The modem being unreachable is shown by every entity becoming unavailable.
    """

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "lte_connected"

    def __init__(self, coordinator: FastMileCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, "lte_connected")

    @property
    def is_on(self) -> bool:
        """Return True when attached to a primary cell."""
        return self.coordinator.data.lte_attached
