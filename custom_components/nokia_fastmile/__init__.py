"""The Nokia FastMile 4G integration."""

from __future__ import annotations

import aiohttp

from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession, async_get_clientsession

from .api import FastMileClient
from .coordinator import FastMileConfigEntry, FastMileCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]


def get_credentials(entry: FastMileConfigEntry) -> tuple[str | None, str | None]:
    """Return the installer credentials (options override the initial data)."""
    username = entry.options.get(CONF_USERNAME, entry.data.get(CONF_USERNAME))
    password = entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD))
    return (username or None), (password or None)


async def async_setup_entry(hass: HomeAssistant, entry: FastMileConfigEntry) -> bool:
    """Set up a receiver from a config entry."""
    username, password = get_credentials(entry)

    session = async_get_clientsession(hass, verify_ssl=False)
    auth_session: aiohttp.ClientSession | None = None
    if username and password:
        # The login cookie must be kept, and the host is an IP address (unsafe=True).
        auth_session = async_create_clientsession(
            hass, verify_ssl=False, cookie_jar=aiohttp.CookieJar(unsafe=True)
        )
        entry.async_on_unload(auth_session.close)

    client = FastMileClient(session, auth_session, entry.data[CONF_HOST], username, password)
    coordinator = FastMileCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_update))
    return True


async def _async_reload_on_update(hass: HomeAssistant, entry: FastMileConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: FastMileConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
