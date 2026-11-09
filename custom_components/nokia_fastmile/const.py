"""Constants for the Nokia FastMile 4G integration."""

from __future__ import annotations

DOMAIN = "nokia_fastmile"

DEFAULT_HOST = "192.168.0.1"
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 15
MAX_SCAN_INTERVAL = 3600
REQUEST_TIMEOUT = 20  # seconds

# After a measurement the modem detaches from the network for a while: poll a few
# times afterwards so that the new neighbor cells show up without waiting.
MEASURE_REFRESH_DELAYS = (30, 90, 180)
REBOOT_REFRESH_DELAYS = (90, 180, 300)
