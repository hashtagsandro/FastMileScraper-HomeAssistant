# Nokia FastMile 4G for Home Assistant

Local-polling integration for the **Nokia FastMile 4G** outdoor receivers (developed against a
4G17-A, firmware `FASTMILE2_D020116B10T0101M01E0115S`). It reads the receiver's own
`status.php` page: no cloud, no MQTT, no add-on, no extra container.

It replaces a "scraper container + REST API" setup with proper entities, devices, a config
flow and a reboot / measure button.

## What you get

| Entity | Notes |
|---|---|
| `sensor.fastmile_rsrp`, `_rssi`, `_rsrq`, `_sinr` | Primary cell signal quality (unavailable while detached) |
| `sensor.fastmile_primary_band`, `_pci`, `_earfcn`, `_frequency`, `_enodeb`, `_cell_id` | Primary cell identity |
| `sensor.fastmile_carrier_aggregation_bands` | e.g. `B1+B3+B7`; attributes: `dl_bands`, `ul_bands`, `secondary_cells` |
| `sensor.fastmile_lte_upload_total`, `_lte_download_total`, `_ethernet_upload_total`, `_ethernet_download_total` | GB since the last restart, **named exactly like the modem's status page** |
| `sensor.fastmile_wan_ip` | First IPv4 given by an APN; attribute `apns` |
| `sensor.fastmile_neighbor_cells` | Count; attribute `cells` (pci, earfcn, band, frequency_mhz, rsrp, rsrq, rssi, sinr). Refreshed by the modem only after a measurement |
| `binary_sensor.fastmile_lte_connected` | On while attached to a primary cell |
| `button.fastmile_measure_cells` | Triggers a neighbor cell measurement |
| `button.fastmile_reboot` | Reboots the modem (only if installer credentials are configured) |
| diagnostics | measurement status, SIM lock status; IMEI and IMSI are created **disabled** |

If the modem cannot be reached, every entity becomes *unavailable*. If it is reachable but not
attached to any cell (for example right after a measurement), the radio sensors are unavailable
while traffic, IP and neighbor cells keep updating.

## Install

**HACS:** add this repository as a custom repository (category *Integration*), download it,
restart Home Assistant. **Manual:** copy `custom_components/nokia_fastmile` into your
`config/custom_components/` folder and restart.

Then *Settings → Devices & services → Add integration → Nokia FastMile 4G*:

* **Host**: the receiver's address (default `192.168.0.1`).
* **Installer username / password** (optional): only needed for the Reboot button, usually
  `fm2-installer`. They are checked with a real login and stored in the config entry. You can add
  or remove them later in the integration's *Configure* dialog, together with the update interval
  (default 60 s).

Home Assistant must be able to route to the modem; with Bridge Mode you need an APN in Router
Mode or a management VLAN (see the FastMileScraper README).

## Replacing the Docker bridge

1. Stop the container, delete the `input_button.fastmile_*` helpers.
2. **Restart Home Assistant** so the state-only entities the container created disappear. If you add
   the integration first, the new entities get a `_2` suffix because the ids are taken.
3. Add the integration. Entity ids keep the `fastmile_` prefix. Differences:

| Old (bridge) | New |
|---|---|
| `binary_sensor.fastmile_online` | gone: use availability of any entity |
| `sensor.fastmile_enb` | `sensor.fastmile_enodeb` |
| `sensor.fastmile_lte_download` / `_lte_upload` | `sensor.fastmile_lte_download_total` / `_lte_upload_total` (see below) |
| `sensor.fastmile_eth_download` / `_eth_upload` | `sensor.fastmile_ethernet_download_total` / `_ethernet_upload_total` |
| `input_button.fastmile_reboot` / `_measure` | `button.fastmile_reboot` / `button.fastmile_measure_cells` |

**About the traffic sensors.** FastMileScraper maps the first counter of each card to *download* and
the second to *upload*, but the status page prints **Upload Total first, then Download Total**.
This integration reads the labels the page shows, so a value now matches what you see in the
modem's web UI. Old "download" sensors were showing the page's *upload* number and vice versa.

## Dashboard example

```yaml
type: entities
title: Nokia FastMile
entities:
  - binary_sensor.fastmile_lte_connected
  - sensor.fastmile_rsrp
  - sensor.fastmile_rsrq
  - sensor.fastmile_sinr
  - sensor.fastmile_primary_band
  - sensor.fastmile_carrier_aggregation_bands
  - sensor.fastmile_wan_ip
  - sensor.fastmile_lte_download_total
  - sensor.fastmile_lte_upload_total
  - button.fastmile_measure_cells
  - button.fastmile_reboot
```

```yaml
type: markdown
title: Neighbor cells
content: |
  {% set cells = state_attr('sensor.fastmile_neighbor_cells', 'cells') or [] %}
  {% if cells | length == 0 %}
  No data yet. Press "Measure cells".
  {% else %}
  | PCI | Band | EARFCN | RSRP | RSRQ | RSSI | SINR |
  |:---:|:---:|:---:|:---:|:---:|:---:|:---:|
  {% for c in cells -%}
  | {{ c.pci }} | {{ 'B' ~ c.band if c.band else '-' }} | {{ c.earfcn }} | {{ c.rsrp }} | {{ c.rsrq }} | {{ c.rssi }} | {{ c.sinr }} |
  {% endfor %}
  {% endif %}
```

## Things to know

* **A measurement drops the cellular connection for roughly 30-60 s** and the modem may need up to
  a few minutes to re-attach. The integration re-reads the status 30, 90 and 180 s afterwards.
* The measurement itself needs no login; only the reboot does.
* Traffic counters are "since last restart" and reset on reboot; they are `total_increasing`
  sensors, so statistics and the Energy-style utility meters cope with the reset.
* Only one action (measure / reboot / credential check) runs at a time.
* IMEI, IMSI, MAC and serial number are redacted from the diagnostics download.

## Development

```
python3 -m unittest discover -s tests -v
```

The parser has no Home Assistant dependency and is tested against a page captured from a 4G17-A
(identifiers replaced). Not covered by the captured page, and reconstructed from FastMileScraper's
selectors: the LTE traffic card and the markup of an *attached* primary cell. If a value is wrong
on your receiver, open `status.php`, save it, remove IMEI/IMSI/MAC/serial and add it as a fixture.

## Credits and license

The page selectors, the login/reboot/measurement requests and the EARFCN table come from
[FastMileScraper](https://github.com/zayigo/FastMileScraper) by zayigo and its fork by
hashtagsandro, released under the GPL-3.0. This integration is a derivative work and is
therefore distributed under the **GPL-3.0** as well: add the license text (`LICENSE`) from that
repository before publishing.
