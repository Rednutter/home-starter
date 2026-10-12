# Fresh Batteries and Your home

Fresh Batteries is an optional preparation checklist. Scan now is always available;
no boxes must be ticked. Return before another scan to wake devices worth keeping.
Powered-off, sleeping and unreachable devices are not treated as retired hardware.

Your home reads floors (when supported), areas, the device and entity registries,
live entity states, config entries and repairs. Rooms expand into devices, then
entities. Disabled entities remain visible and do not count as offline. Entities
without a registry device remain available under technical details. No independent
LAN discovery is performed.

Findings have confidence and reasons:

- **Needs a room:** no device area in a successfully read area registry. A room-name
  match is Plausible; one consistent related-entity area is Plausible, or High
  confidence with two or more entities. Conflicting evidence yields no suggestion.
- **Needs attention:** failed integration, active repair, disabled device/configuration
  (possibly intentional), or at least two unavailable enabled entities / all enabled
  entities unavailable during this snapshot. Disabled entity values are excluded.
- **Possible duplicate:** an exact shared namespaced identifier or connection,
  including normalized MAC. Confidence is Plausible: HA intentionally represents
  one physical device through multiple integrations. No merge is proposed. Similar
  names/model alone are deliberately insufficient. Child identifier namespaces are
  excluded. Parent/child, siblings and via-device relationships are displayed.
- **Possibly offline:** all enabled entities unavailable *and* a failed owning
  integration. Retirement confidence remains Unknown. Wake/power, then check again.
- **Already fine:** required sources were readable, owning integrations loaded, and
  all enabled device entities had usable observed states. This is snapshot health,
  not proof of hardware correctness or future availability.

Only **assign device to area** is implemented. Review shows the device and old/new
room; confirmation sends one exact `area_id` update to Core. The server verifies
the ingress user's administrator role, rereads current device/area state, rejects
stale preconditions, writes only that field, then rereads the registry. Transport
failure or unchanged state never claims success. Check again before retrying an
uncertain write. Writes are serialized within Home Starter. HA's update API has no
atomic compare-and-swap, so concurrent changes made outside the App cannot be
fully prevented. Entity-specific area overrides are kept and shown.

HA **2026.10.0** `config/device_registry/list` includes main and child devices;
`config_entry_id` identifies the owning integration, with legacy `config_entries`
also accepted. `parent_device_id` establishes children and siblings. HA's linked
devices command defines linkage as shared identity/connection; this implementation
reconciles those fields locally instead of making one extra API request per device.
An unsupported floor command is reported as unavailable while room/device data
continues to work. Counts are HA registry devices, including logical/service devices,
not a deduplicated count of physical objects. The scan cannot establish historical
availability or whether a person intentionally retired a device.

Anything else around the house offers reminders and possible future uses. Choices
are page-local, reset on reload, and aren't an external asset database. SIP, calendars,
clients, discovery, firmware, renaming, merging and removal are intentionally deferred.

Permissions are unchanged: ingress only, Core API proxy and Supervisor manager for
the existing Music Assistant setup. No browser tokens, database, Docker socket,
host network/mount or broad host permission was added.
