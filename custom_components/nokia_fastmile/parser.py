"""Parser for the status page (``status.php``) of Nokia FastMile 4G receivers.

The selectors follow the ones of FastMileScraper (https://github.com/zayigo/FastMileScraper,
GPL-3.0), verified against the 4G17-A receiver. This module has no Home Assistant
dependency so it can be unit tested on its own.

Differences from the original library:
* a receiver that is not attached to any LTE cell ("No Cell available") is a valid
  state, not an error (``primary`` is simply ``None``);
* traffic counters are read by the labels the page shows ("Upload Total" /
  "Download Total") instead of by position;
* the measurement status shown next to "Available cells" is exposed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from bs4 import BeautifulSoup, Comment, Tag

from .earfcn import earfcn_to_band, earfcn_to_frequency
from .exceptions import FastMileAuthError, FastMileParseError

# Decimal units, like the modem's own conversion (1 GB = 1000 MB).
_UNIT_TO_GB: dict[str, float] = {"B": 1e-9, "KB": 1e-6, "MB": 1e-3, "GB": 1.0, "TB": 1e3}
_CELL_COLUMNS = 7  # PCI, eARFCN, cell type, RSRP, RSRQ, RSSI, SINR (CINR)


@dataclass(frozen=True, slots=True)
class Cell:
    """Signal values of one LTE cell."""

    pci: int | None
    earfcn: int | None
    band: int | None
    frequency_mhz: float | None
    rsrp: int | None
    rsrq: int | None
    rssi: int | None
    sinr: int | None

    def as_dict(self) -> dict[str, int | float | None]:
        """Return the cell as a plain dict."""
        return asdict(self)


@dataclass(slots=True)
class FastMileStatus:
    """Everything the status page tells about the receiver."""

    model: str | None = None
    sw_version: str | None = None
    serial_number: str | None = None
    imei: str | None = None
    imsi: str | None = None
    mac: str | None = None
    lock_status: str | None = None
    apns: list[dict[str, str | None]] = field(default_factory=list)
    lte_upload_gb: float | None = None
    lte_download_gb: float | None = None
    eth_upload_gb: float | None = None
    eth_download_gb: float | None = None
    enb: int | None = None
    cell_id: int | None = None
    primary_band: int | None = None
    dl_bands: list[int] = field(default_factory=list)
    ul_bands: list[int] = field(default_factory=list)
    primary: Cell | None = None
    secondary: list[Cell] = field(default_factory=list)
    available: list[Cell] = field(default_factory=list)
    measurement_status: str | None = None

    @property
    def lte_attached(self) -> bool:
        """Return True when the receiver is attached to a primary cell."""
        return self.primary is not None

    @property
    def wan_ip(self) -> str | None:
        """Return the first IPv4 address assigned by an APN."""
        return next((apn["ipv4"] for apn in self.apns if apn.get("ipv4")), None)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    value = tag.get_text(strip=True)
    return value or None


def _int(value: Tag | str | None) -> int | None:
    text = value.get_text(strip=True) if isinstance(value, Tag) else value
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


def _parse_used_data(text: str | None) -> float | None:
    """Convert e.g. ``3.54GB`` or ``0.19 MB`` to gigabytes."""
    if not text:
        return None
    match = re.search(r"([\d.]+)\s*([A-Za-z]+)", text)
    if not match:
        return None
    factor = _UNIT_TO_GB.get(match.group(2).upper())
    if factor is None:
        return None
    try:
        return round(float(match.group(1)) * factor, 6)
    except ValueError:
        return None


def _parse_traffic(soup: BeautifulSoup, card_class: str) -> dict[str, float | None]:
    """Return ``{"upload": GB, "download": GB}`` of the LTE or Ethernet card."""
    result: dict[str, float | None] = {"upload": None, "download": None}
    card = soup.find(class_=card_class)
    if card is None:
        return result

    for label in card.find_all(class_="subtitle-value"):
        name = label.get_text(strip=True).lower()
        value = label.find_next(class_="bytes")
        gigabytes = _parse_used_data(_text(value))
        if name.startswith("upload"):
            result["upload"] = gigabytes
        elif name.startswith("download"):
            result["download"] = gigabytes

    if result["upload"] is None and result["download"] is None:
        # Labels missing: the page lists upload first, then download.
        counters = card.find_all(class_="bytes")
        if len(counters) >= 2:
            result["upload"] = _parse_used_data(_text(counters[0]))
            result["download"] = _parse_used_data(_text(counters[1]))
    return result


def _parse_bands(tag: Tag | None) -> list[int]:
    text = _text(tag) or ""
    if not text or "not available" in text.lower():
        return []
    bands: list[int] = []
    for part in text.split("+"):
        match = re.search(r"\d+", part)
        if match:
            bands.append(int(match.group()))
    return bands


def _section_values(soup: BeautifulSoup, comment_text: str) -> list[Tag]:
    """Return the value cells of the card that follows an HTML comment."""
    comment = soup.find(string=lambda t: isinstance(t, Comment) and t.strip() == comment_text)
    if comment is None:
        return []
    section = comment.find_next_sibling("div")
    if section is None:
        return []
    return section.find_all(class_="name-of-value-in-card-bold")


def _cell_from_values(values: list[Tag]) -> Cell:
    earfcn = _int(values[1])
    return Cell(
        pci=_int(values[0]),
        earfcn=earfcn,
        band=earfcn_to_band(earfcn) if earfcn is not None else None,
        frequency_mhz=earfcn_to_frequency(earfcn) if earfcn is not None else None,
        rsrp=_int(values[3]),
        rsrq=_int(values[4]),
        rssi=_int(values[5]),
        sinr=_int(values[6]),
    )


def _parse_apns(soup: BeautifulSoup) -> list[dict[str, str | None]]:
    comment = soup.find(string=lambda t: isinstance(t, Comment) and t.strip() == "APNs card")
    section = comment.find_next_sibling("div") if comment else None
    if section is None:
        return []

    headers = {"access point name", "ipv4 address", "ipv6 address"}
    values = [
        div.get_text(strip=True)
        for div in section.find_all("div")
        if div.find("div") is None and div.get_text(strip=True).lower() not in headers
    ]
    apns: list[dict[str, str | None]] = []
    for offset in range(0, len(values) - 2, 3):
        ipv4, ipv6 = values[offset + 1], values[offset + 2]
        apns.append(
            {
                "name": values[offset],
                "ipv4": None if ipv4 in ("", "::") else ipv4,
                "ipv6": None if ipv6 in ("", "::") else ipv6,
            }
        )
    return apns


def _parse_available_cells(soup: BeautifulSoup) -> list[Cell]:
    cells: list[Cell] = []
    index = 0
    while (pci := soup.find(id=f"available-cell-id-{index}")) is not None:
        earfcn = _int(soup.find(id=f"available-earfcn-{index}"))
        if _int(pci) is not None:
            cells.append(
                Cell(
                    pci=_int(pci),
                    earfcn=earfcn,
                    band=earfcn_to_band(earfcn) if earfcn is not None else None,
                    frequency_mhz=earfcn_to_frequency(earfcn) if earfcn is not None else None,
                    rsrp=_int(soup.find(id=f"rsrp-{index}")),
                    rsrq=_int(soup.find(id=f"rsrq-{index}")),
                    rssi=_int(soup.find(id=f"rssi-{index}")),
                    sinr=_int(soup.find(id=f"sinr-{index}")),
                )
            )
        index += 1
    return cells


def _parse_measurement_status(soup: BeautifulSoup) -> str | None:
    tag = soup.find(class_="value-in-card-title-left")
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    text = re.sub(r"^\s*status:\s*", "", text, flags=re.IGNORECASE)
    return text or None


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def parse_status(html: str) -> FastMileStatus:
    """Parse the HTML of ``status.php``."""
    soup = BeautifulSoup(html, "html.parser")

    if soup.find(id="model-value") is None and soup.find(id="attached-cell-val") is None:
        raise FastMileParseError("The page is not a Nokia FastMile status page")

    status = FastMileStatus(
        model=_text(soup.find(id="model-value")),
        sw_version=_text(soup.find(id="software-version-val")),
        serial_number=_text(soup.find(id="sn-value")),
        imei=_text(soup.find(id="imei-value")),
        imsi=_text(soup.find(id="imsi-name-value")),
        mac=_text(soup.find(id="eth-mac-value")),
        lock_status=_text(soup.find(id="lockStatus-name-value")),
        apns=_parse_apns(soup),
        measurement_status=_parse_measurement_status(soup),
    )

    lte = _parse_traffic(soup, "LTE")
    eth = _parse_traffic(soup, "Ethernet")
    status.lte_upload_gb, status.lte_download_gb = lte["upload"], lte["download"]
    status.eth_upload_gb, status.eth_download_gb = eth["upload"], eth["download"]

    attached = soup.find(id="attached-cell-val")
    spans = attached.find_all("span") if attached is not None else []
    if len(spans) >= 3:
        status.enb = _int(spans[0])
        status.cell_id = _int(spans[1])
        status.primary_band = _int(spans[2])

    ca_dl = _parse_bands(soup.find(id="bandDL-val"))
    ca_ul = _parse_bands(soup.find(id="bandUL-val"))
    if status.primary_band is not None:
        status.dl_bands = [status.primary_band, *ca_dl]
        status.ul_bands = [status.primary_band, *ca_ul]
    else:
        status.dl_bands, status.ul_bands = ca_dl, ca_ul

    primary_values = _section_values(soup, "Primary Cell information card")
    if len(primary_values) >= _CELL_COLUMNS:
        primary = _cell_from_values(primary_values[:_CELL_COLUMNS])
        if primary.pci is not None or primary.earfcn is not None:
            status.primary = primary

    secondary_values = _section_values(soup, "Secondary Cell information card")
    for offset in range(0, len(secondary_values) - _CELL_COLUMNS + 1, _CELL_COLUMNS):
        status.secondary.append(_cell_from_values(secondary_values[offset : offset + _CELL_COLUMNS]))

    status.available = _parse_available_cells(soup)
    return status


def parse_network_token(html: str) -> str:
    """Check that a login succeeded and return the CSRF token of ``network.php``."""
    soup = BeautifulSoup(html, "html.parser")
    logout = soup.find(id="logout")
    if logout is None or "Welcome" not in logout.get_text():
        raise FastMileAuthError("Login rejected or session expired")
    token = soup.find("input", {"name": "token"})
    return str(token.get("value", "")) if token is not None else ""
