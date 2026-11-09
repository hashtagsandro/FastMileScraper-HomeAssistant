"""Data update coordinator for the Nokia FastMile 4G integration."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FastMileClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .exceptions import FastMileConnectionError, FastMileParseError
from .parser import FastMileStatus, parse_status

_LOGGER = logging.getLogger(__name__)

type FastMileConfigEntry = ConfigEntry[FastMileCoordinator]


class FastMileCoordinator(DataUpdateCoordinator[FastMileStatus]):
    """Poll status.php and share the result with all entities."""

    config_entry: FastMileConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: FastMileConfigEntry,
        client: FastMileClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.client = client

    async def _async_update_data(self) -> FastMileStatus:
        try:
            html = await self.client.async_get_status_html()
            return await self.hass.async_add_executor_job(parse_status, html)
        except FastMileConnectionError as err:
            raise UpdateFailed(f"Cannot reach the modem at {self.client.host}: {err}") from err
        except FastMileParseError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def async_schedule_refreshes(self, delays: Iterable[int]) -> None:
        """Refresh a few times after a measurement or a reboot."""

        async def _refresh(_now: datetime) -> None:
            await self.async_request_refresh()

        for delay in delays:
            self.config_entry.async_on_unload(async_call_later(self.hass, delay, _refresh))
