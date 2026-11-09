"""Exceptions raised by the Nokia FastMile 4G integration."""

from __future__ import annotations


class FastMileError(Exception):
    """Base error."""


class FastMileConnectionError(FastMileError):
    """The modem cannot be reached or answered with an unexpected status."""


class FastMileAuthError(FastMileError):
    """Missing or rejected installer credentials."""


class FastMileParseError(FastMileError):
    """The page is not a FastMile status page."""


class FastMileBusyError(FastMileError):
    """Another modem action is already running."""
