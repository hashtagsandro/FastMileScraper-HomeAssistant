"""Buttons of the Nokia FastMile 4G integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import MEASURE_REFRESH_DELAYS, REBOOT_REFRESH_DELAYS
from .coordinator import FastMileConfigEntry, FastMileCoordinator
from .entity import FastMileEntity
from .exceptions import FastMileAuthError, FastMileBusyError, FastMileError

MEASURE = ButtonEntityDescription(key="measure", translation_key="measure", icon="mdi:radar")
REBOOT = ButtonEntityDescription(
    key="reboot", translation_key="reboot", device_class=ButtonDeviceClass.RESTART
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FastMileConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data
    entities = [FastMileButton(coordinator, MEASURE)]
    if coordinator.client.has_credentials:
        entities.append(FastMileButton(coordinator, REBOOT))
    async_add_entities(entities)


class FastMileButton(FastMileEntity, ButtonEntity):
    """Trigger a measurement or reboot the receiver."""

    def __init__(self, coordinator: FastMileCoordinator, description: ButtonEntityDescription) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        """Run the action on the modem."""
        client = self.coordinator.client
        reboot = self.entity_description.key == "reboot"
        try:
            if reboot:
                await client.async_reboot()
            else:
                await client.async_trigger_measurement()
        except FastMileBusyError as err:
            raise HomeAssistantError(str(err)) from err
        except FastMileAuthError as err:
            raise HomeAssistantError(f"Installer login rejected by the modem: {err}") from err
        except FastMileError as err:
            raise HomeAssistantError(f"The modem did not accept the request: {err}") from err

        self.coordinator.async_schedule_refreshes(REBOOT_REFRESH_DELAYS if reboot else MEASURE_REFRESH_DELAYS)
