"""Sensors of the Nokia FastMile 4G integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfFrequency,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import FastMileConfigEntry, FastMileCoordinator
from .entity import FastMileEntity
from .parser import FastMileStatus


@dataclass(frozen=True, kw_only=True)
class FastMileSensorDescription(SensorEntityDescription):
    """Describe a FastMile sensor."""

    value_fn: Callable[[FastMileStatus], StateType]
    available_fn: Callable[[FastMileStatus], bool] = lambda _: True
    attrs_fn: Callable[[FastMileStatus], dict[str, Any]] | None = None


def _primary(attr: str) -> Callable[[FastMileStatus], StateType]:
    return lambda s: getattr(s.primary, attr) if s.primary is not None else None


def _attached(s: FastMileStatus) -> bool:
    return s.primary is not None


def _primary_band(s: FastMileStatus) -> str | None:
    band = s.primary_band if s.primary_band is not None else (s.primary.band if s.primary else None)
    return f"B{band}" if band is not None else None


def _ca_bands(s: FastMileStatus) -> str | None:
    return "+".join(f"B{band}" for band in s.dl_bands) or None


SENSORS: tuple[FastMileSensorDescription, ...] = (
    # --- primary cell radio quality ---
    FastMileSensorDescription(
        key="rsrp",
        translation_key="rsrp",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_primary("rsrp"),
        available_fn=_attached,
    ),
    FastMileSensorDescription(
        key="rssi",
        translation_key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_primary("rssi"),
        available_fn=_attached,
    ),
    FastMileSensorDescription(
        key="rsrq",
        translation_key="rsrq",
        icon="mdi:signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_primary("rsrq"),
        available_fn=_attached,
    ),
    FastMileSensorDescription(
        key="sinr",
        translation_key="sinr",
        icon="mdi:signal-variant",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_primary("sinr"),
        available_fn=_attached,
    ),
    # --- primary cell identity ---
    FastMileSensorDescription(
        key="primary_band",
        translation_key="primary_band",
        icon="mdi:antenna",
        value_fn=_primary_band,
        available_fn=lambda s: _primary_band(s) is not None,
    ),
    FastMileSensorDescription(
        key="ca_bands",
        translation_key="ca_bands",
        icon="mdi:transit-connection-variant",
        value_fn=_ca_bands,
        available_fn=lambda s: bool(s.dl_bands),
        attrs_fn=lambda s: {
            "dl_bands": s.dl_bands,
            "ul_bands": s.ul_bands,
            "secondary_cells": [cell.as_dict() for cell in s.secondary],
        },
    ),
    FastMileSensorDescription(
        key="pci",
        translation_key="pci",
        icon="mdi:cell-tower",
        value_fn=_primary("pci"),
        available_fn=_attached,
    ),
    FastMileSensorDescription(
        key="earfcn",
        translation_key="earfcn",
        icon="mdi:radio-tower",
        value_fn=_primary("earfcn"),
        available_fn=_attached,
    ),
    FastMileSensorDescription(
        key="frequency",
        translation_key="frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_primary("frequency_mhz"),
        available_fn=_attached,
    ),
    FastMileSensorDescription(
        key="enb",
        translation_key="enb",
        icon="mdi:cell-tower",
        value_fn=lambda s: s.enb,
        available_fn=lambda s: s.enb is not None,
    ),
    FastMileSensorDescription(
        key="cell_id",
        translation_key="cell_id",
        icon="mdi:identifier",
        value_fn=lambda s: s.cell_id,
        available_fn=lambda s: s.cell_id is not None,
    ),
    # --- traffic since the last restart, as labelled on the modem's status page ---
    *(
        FastMileSensorDescription(
            key=key,
            translation_key=key,
            device_class=SensorDeviceClass.DATA_SIZE,
            native_unit_of_measurement=UnitOfInformation.GIGABYTES,
            state_class=SensorStateClass.TOTAL_INCREASING,
            suggested_display_precision=3,
            value_fn=lambda s, attr=attr: getattr(s, attr),
            available_fn=lambda s, attr=attr: getattr(s, attr) is not None,
        )
        for key, attr in (
            ("lte_upload", "lte_upload_gb"),
            ("lte_download", "lte_download_gb"),
            ("eth_upload", "eth_upload_gb"),
            ("eth_download", "eth_download_gb"),
        )
    ),
    # --- network ---
    FastMileSensorDescription(
        key="wan_ip",
        translation_key="wan_ip",
        icon="mdi:ip-network",
        value_fn=lambda s: s.wan_ip,
        available_fn=lambda s: s.wan_ip is not None,
        attrs_fn=lambda s: {"apns": s.apns},
    ),
    # --- neighbor cells (updated only after a measurement) ---
    FastMileSensorDescription(
        key="neighbor_cells",
        translation_key="neighbor_cells",
        icon="mdi:radar",
        value_fn=lambda s: len(s.available),
        attrs_fn=lambda s: {"cells": [cell.as_dict() for cell in s.available]},
    ),
    FastMileSensorDescription(
        key="measurement_status",
        translation_key="measurement_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.measurement_status,
        available_fn=lambda s: s.measurement_status is not None,
    ),
    # --- diagnostics ---
    FastMileSensorDescription(
        key="lock_status",
        translation_key="lock_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:lock",
        value_fn=lambda s: s.lock_status,
        available_fn=lambda s: s.lock_status is not None,
    ),
    FastMileSensorDescription(
        key="imei",
        translation_key="imei",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:sim-alert",
        value_fn=lambda s: s.imei,
        available_fn=lambda s: s.imei is not None,
    ),
    FastMileSensorDescription(
        key="imsi",
        translation_key="imsi",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        icon="mdi:sim",
        value_fn=lambda s: s.imsi,
        available_fn=lambda s: s.imsi is not None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FastMileConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    async_add_entities(FastMileSensor(coordinator, description) for description in SENSORS)


class FastMileSensor(FastMileEntity, SensorEntity):
    """A FastMile sensor."""

    entity_description: FastMileSensorDescription
    # Bulky attributes that change rarely: keep them out of the recorder database.
    _unrecorded_attributes = frozenset({"cells", "secondary_cells", "apns"})

    def __init__(self, coordinator: FastMileCoordinator, description: FastMileSensorDescription) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return True when the modem answers and the value exists."""
        return super().available and self.entity_description.available_fn(self.coordinator.data)

    @property
    def native_value(self) -> StateType:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        attrs_fn = self.entity_description.attrs_fn
        return attrs_fn(self.coordinator.data) if attrs_fn else None
