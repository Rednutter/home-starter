# Waste Collection / Bin Context

Waste is household context, not a commitment or synthetic calendar event. The
first provider is Wodonga Council. There is no nationwide provider framework.

## Provider and authority

`wodonga.py` obtains public source data; `waste.py` owns confirmed household intent,
normalized services, dated collections, provenance and relevance. `waste_runtime.py`
prepares supported native Template helpers and publishes expiring context state.
Services have an ID, label and cadence; collections contain service IDs, so a
Council-specific stream can be represented without another entity per stream.

- [Council bins and collection](https://www.wodonga.vic.gov.au/Services/Recycling-and-Waste/Bins-and-Collection)
  establishes weekly green and alternating fortnightly recycling/general service,
  and links the annual calendar.
- [Council FAQ](https://www.wodonga.vic.gov.au/Services/Recycling-and-Waste/Recycling-centre/Recycling-and-waste-FAQs)
  confirms normal public-holiday collection days.
- [Official ArcGIS item](https://www.arcgis.com/home/item.html?id=f22429353e8a4552945dfa39684e6bc8)
  supplies collection polygons/day. The stable item resolves the current service
  URL; no temporary FeatureServer host is embedded. Attribution: City of Wodonga,
  public collection-area data, CC BY 4.0 as stated in item metadata.
- The linked official annual PDF supplies the **dated** red/yellow pattern and
  night-before/by-6am guidance. Its URL and SHA-256 version are retained with the
  year and January–December validity. No anchor is extrapolated into another year.

The server downloads public polygons and matches HA's home point locally. It
retains only day/zone and map version, never the home point, address, full map or
PDF. A known-weekday fallback is explicitly marked owner-confirmed. Requests do
not contain household coordinates. Public URL/redirect hosts and response sizes
are bounded. Unknown layouts, partial dates, contradictory weeks, changed day or
zone, and changed overlapping schedules require review rather than a guessed result.

The current PDF decoder recognizes the verified Council A5 layout and service
legend, checks month/year/date geometry and every weekday in the printed year.
It fails closed on a changed layout. Future calendars are discovered from the
official page, not presumed to share a previous year's parity.

## Setup, persistence and failure

Open **Waste collection**, check the Council service, review day/next bins and
optional target screens, then **Confirm service and create bin entities**. A preview
does not save household configuration or write HA resources. Confirmation uses
the normal administrator, revision and expiring-preview boundary.

Private `waste-collection.json` stores only intent, bounded annual dates, evidence
and owned helper identities. Absent waste state migrates lazily without rewriting
household, readiness, Music, calendars, screen identity, preferences or publications.
Unsupported/corrupt state is preserved and reported. Existing legacy calendar
choices remain saved; provider-selected screens use bin context instead, while
unselected screens retain their previous behavior.

Sources refresh daily; an outage retries hourly. Last-valid data remains usable
for at most seven days after verification and only within annual validity, with
an explicit outage label. Stale/expired/conflicting evidence suppresses confident
dates and shows **Bin schedule needs checking**. Refresh failure never erases the
last verified schedule. Renewal is flagged 45 days before year end; a missing new
year is never manufactured. Cached evidence survives app restarts.

## HA and presentation

Six helpers are created through HA's native Template config flow:

- `sensor.home_starter_next_bin_collection`
- `sensor.home_starter_next_bin_types`
- `sensor.home_starter_bin_collection_day`
- `sensor.home_starter_bin_days_until`
- `binary_sensor.home_starter_bin_night`
- `sensor.home_starter_bin_context`

The additional owned ephemeral `sensor.home_starter_bin_source` carries next and
following collection, services, provider, sources, freshness, verification times
and expiry. HA may record these non-address attributes. The app refreshes its
heartbeat every minute; native helper availability expires after projection
stops (within HA's next minute evaluation). A restart rehydrates it from private
evidence. Partial/uncertain helper creation is retained for inspection; retries
do not create duplicates. External edits, entity renames, disabled/missing helpers
and ownership collisions stop updates without overwriting user resources.

In the household timezone, **Bins tonight** appears from 18:00 the evening before;
**Bins out this morning** continues until 06:00. Then attention expires and the
next collection advances. Expiry does not claim collection or completion. Quiet
screens reserve no bin card/section. Stale warnings remain explicit.

Contextual wall projections can include selected bin context. Tablet/phone touch
surfaces gain a conditional section only through explicit generate/review/publish.
Saving a waste service never republishes existing dashboards. HA entities are
available for later automations, but this feature creates no automations or events.

## Validation and live boundary

Focused tests cover weekly/alternating collections, morning expiry, week/year
boundaries, leap years, holidays, source parsing and renewal, outages/conflicts,
privacy, migration, restart, native ownership, context and screen selection.
Committed fixtures are fictional.

`devtools/accept_waste_native.py` exercises real Template config flows and helper
states on disposable HA 2026.10.0, browser setup/confirmation, native evening,
morning, quiet and stale displays, heartbeat expiry and app restart persistence.
Existing Python/JavaScript, browser, context, dashboard and screen-identity suites
provide regression coverage. Visual review returned ship after action spacing was
aligned with existing controls. These fixtures do not verify the real household.

Release validation: 510 Python tests, 18 JavaScript tests, Ruff lint/format,
existing desktop/mobile browser flows, native surface/context/screen-identity
regressions and the new native waste acceptance passed. Public release CI also
checks the App manifest and builds amd64/arm64 images.

The actual Green must first be inspected read-only. A Council match and calendar
preview are a proposal until the owner confirms service and target screens through
Home Starter. Existing dashboards remain unchanged unless separately reviewed and
published. Physical screen commissioning is still a separate workflow.
