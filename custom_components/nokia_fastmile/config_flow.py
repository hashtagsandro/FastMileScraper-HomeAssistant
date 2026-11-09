"""Config flow for the Nokia FastMile 4G integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_create_clientsession, async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import FastMileClient
from .const import (
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .exceptions import FastMileAuthError, FastMileConnectionError, FastMileParseError
from .parser import parse_status

_LOGGER = logging.getLogger(__name__)

_PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="off"))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): _PASSWORD,
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=5,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_USERNAME): str,
        vol.Optional(CONF_PASSWORD): _PASSWORD,
    }
)


async def _async_check_credentials(
    hass: HomeAssistant, host: str, username: str, password: str
) -> str | None:
    """Try an installer login; return an error key or None when it works."""
    auth_session = async_create_clientsession(
        hass, verify_ssl=False, cookie_jar=aiohttp.CookieJar(unsafe=True)
    )
    client = FastMileClient(
        async_get_clientsession(hass, verify_ssl=False), auth_session, host, username, password
    )
    try:
        await client.async_check_credentials()
    except FastMileAuthError:
        return "invalid_auth"
    except FastMileConnectionError:
        return "cannot_connect"
    finally:
        await auth_session.close()
    return None


class FastMileConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup of a receiver."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FastMileOptionsFlow:
        """Return the options flow."""
        return FastMileOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the address (and optionally the installer account)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            username = (user_input.get(CONF_USERNAME) or "").strip()
            password = user_input.get(CONF_PASSWORD) or ""

            client = FastMileClient(async_get_clientsession(self.hass, verify_ssl=False), None, host)
            status = None
            try:
                html = await client.async_get_status_html()
                status = await self.hass.async_add_executor_job(parse_status, html)
            except FastMileConnectionError:
                errors["base"] = "cannot_connect"
            except FastMileParseError:
                errors["base"] = "invalid_response"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while contacting the modem")
                errors["base"] = "unknown"

            if status is not None and bool(username) != bool(password):
                errors["base"] = "credentials_incomplete"
            elif status is not None and username:
                if error := await _async_check_credentials(self.hass, host, username, password):
                    errors["base"] = error

            if status is not None and not errors:
                unique_id = dr.format_mac(status.mac) if status.mac else (status.serial_number or host)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                data: dict[str, Any] = {CONF_HOST: host}
                if username:
                    data[CONF_USERNAME] = username
                    data[CONF_PASSWORD] = password
                return self.async_create_entry(title=f"FastMile ({host})", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )


class FastMileOptionsFlow(OptionsFlow):
    """Scan interval and installer account."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        entry = self.config_entry
        errors: dict[str, str] = {}

        if user_input is not None:
            username = (user_input.get(CONF_USERNAME) or "").strip()
            password = user_input.get(CONF_PASSWORD) or ""
            if bool(username) != bool(password):
                errors["base"] = "credentials_incomplete"
            elif username and (
                error := await _async_check_credentials(self.hass, entry.data[CONF_HOST], username, password)
            ):
                errors["base"] = error

            if not errors:
                return self.async_create_entry(
                    data={
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    }
                )

        current = user_input or {
            CONF_SCAN_INTERVAL: entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            CONF_USERNAME: entry.options.get(CONF_USERNAME, entry.data.get(CONF_USERNAME, "")),
            CONF_PASSWORD: entry.options.get(CONF_PASSWORD, entry.data.get(CONF_PASSWORD, "")),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, current),
            errors=errors,
        )
