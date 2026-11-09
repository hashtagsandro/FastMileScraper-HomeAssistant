"""Async client for the web interface of a Nokia FastMile 4G receiver.

* status page and cell measurement need no login;
* reboot needs the installer account: login.php -> CSRF token from network.php ->
  restart.php (same flow as FastMileScraper).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator

import aiohttp

from .const import REQUEST_TIMEOUT
from .exceptions import (
    FastMileAuthError,
    FastMileBusyError,
    FastMileConnectionError,
)
from .parser import parse_network_token

_LOGGER = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)


class FastMileClient:
    """Talk to the receiver over HTTPS (self-signed certificate)."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth_session: aiohttp.ClientSession | None,
        host: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the client.

        ``session`` is used for everything that needs no login. ``auth_session`` must
        have its own cookie jar (``CookieJar(unsafe=True)``: the host is an IP address).
        """
        self._session = session
        self._auth_session = auth_session
        self.host = host
        self._username = username
        self._password = password
        self._action_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        """Return the base URL of the web interface."""
        return f"https://{self.host}"

    @property
    def has_credentials(self) -> bool:
        """Return True when installer credentials are configured."""
        return bool(self._auth_session and self._username and self._password)

    @contextlib.asynccontextmanager
    async def _exclusive(self) -> AsyncIterator[None]:
        if self._action_lock.locked():
            raise FastMileBusyError("Another action on the modem is already in progress")
        async with self._action_lock:
            yield

    # -- no login needed ----------------------------------------------------
    async def async_get_status_html(self) -> str:
        """Return the HTML of status.php."""
        try:
            async with self._session.get(f"{self.base_url}/status.php", timeout=_TIMEOUT) as resp:
                if resp.status != 200:
                    raise FastMileConnectionError(f"Unexpected HTTP status {resp.status}")
                return await resp.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FastMileConnectionError(str(err) or type(err).__name__) from err

    async def async_trigger_measurement(self) -> None:
        """Start a neighbor cell measurement (the modem detaches for 30-60 s)."""
        async with self._exclusive():
            try:
                async with self._session.post(
                    f"{self.base_url}/measurements.php",
                    data={"Submit": "Trigger"},
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status != 200:
                        raise FastMileConnectionError(f"Measurement refused: HTTP {resp.status}")
            except (aiohttp.ClientError, TimeoutError) as err:
                raise FastMileConnectionError(str(err) or type(err).__name__) from err

    # -- installer login needed ---------------------------------------------
    async def _login(self) -> str:
        """Log in and return the CSRF token."""
        if not self.has_credentials or self._auth_session is None:
            raise FastMileAuthError("No installer credentials configured")
        try:
            async with self._auth_session.post(
                f"{self.base_url}/login.php",
                data={
                    "access_login": self._username,
                    "access_password": self._password,
                    "submit": "Login",
                },
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    raise FastMileAuthError(f"Login failed: HTTP {resp.status}")
            async with self._auth_session.get(f"{self.base_url}/network.php", timeout=_TIMEOUT) as resp:
                html = await resp.text(errors="replace")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise FastMileConnectionError(str(err) or type(err).__name__) from err
        return parse_network_token(html)

    async def _logout(self, token: str) -> None:
        if self._auth_session is None:
            return
        with contextlib.suppress(aiohttp.ClientError, TimeoutError):
            async with self._auth_session.post(
                f"{self.base_url}/network.php",
                data={"logout": "logout", "token": token},
                timeout=_TIMEOUT,
            ):
                pass

    async def async_check_credentials(self) -> None:
        """Log in and out again; raises FastMileAuthError when rejected."""
        async with self._exclusive():
            token = await self._login()
            await self._logout(token)

    async def async_reboot(self) -> None:
        """Reboot the receiver."""
        async with self._exclusive():
            token = await self._login()
            try:
                async with self._auth_session.post(  # type: ignore[union-attr]
                    f"{self.base_url}/restart.php",
                    data={"token": token, "Submit": "Reboot"},
                    timeout=_TIMEOUT,
                ) as resp:
                    if resp.status != 200:
                        raise FastMileConnectionError(f"Reboot refused: HTTP {resp.status}")
            except (aiohttp.ClientError, TimeoutError):
                # The modem drops the connection as soon as it restarts.
                _LOGGER.debug("Connection closed by the modem while rebooting (expected)")
