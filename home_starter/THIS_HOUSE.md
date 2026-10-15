# This House

Home Assistant owns people, trackers, floors, areas, devices and entities. This
House reads those records live. It does not maintain a second household registry.
Existing screen profiles remain saved display preferences, distinct from HA people.

Confirm existing Person records as adult, child or display/other account, and
compare their assigned trackers. Roles affect the commissioning count only, never
HA login permissions. Tracker ownership and pairing use native Person settings.
Reporting presence is not proof of ownership or reliable presence detection.

Presence is optional. An existing household member can be confirmed as intentionally
untracked; this is an accepted choice, not unfinished setup. Missing tracking never
establishes home or away. The private choice references the HA Person and reopens
when their name or assigned trackers change. It does not enable tracking or change
HA's Person state, records, accounts or permissions.

Review floor and area names and assignments before saving. Changes use supported
`config/floor_registry` and `config/area_registry` create/update commands. Existing
IDs and other metadata remain intact. Existing areas that represent several rooms
or a whole level can be marked as groups without changing HA's record. They stay
available to existing controls, but are excluded as individual equipment locations.

Physical equipment is shown at device level. Service records are excluded, shared
Google Cast groups are identified, and portable equipment can be confirmed without
inventing a fixed room. Already placed devices need no routine interaction. Review
attention separately: availability, duplicate names and entity overrides do not
establish physical function or justify deletion.

Equipment serving several rooms can be confirmed separately after recording its
coverage in a physical note. This keeps a combined climate zone out of missing-room
work without assigning it to an invented room. Its console/controller still has a
separate physical location to review. Native record changes reopen this intent.

Device placement writes only `area_id` through `config/device_registry/update`.
Names, entity IDs, integrations and entity-level area overrides are preserved.
The app checks the live record against the reviewed signature, then reads back
the result. Concurrent native HA changes reopen affected confirmations. An
uncertain write reports the uncertainty and requires a fresh review.

Short physical connection/function notes can record useful facts that HA cannot
naturally express. Do not enter passwords or sensitive account information.
Private `house-confirmations.json` stores referenced HA IDs, reviewed signatures,
roles/grouping intent, notes and bounded change history; it is excluded from Git.
Read-only inspection creates no confirmation file. Corrupt saved data fails closed.
Normal setup reset preserves these confirmations because it does not reset HA's
physical registry. Existing Music credentials/proof and dashboards are independent.

Structure confirmation requires the user to compare the complete list with the
real home. A floorplan supplies evidence, not permission to guess room occupancy,
device wiring or placement. Capability planning follows the reconciled house model;
this version does not implement a new set of household outcome features.

## Room inspection and readiness (0.5.4)

Rooms and their equipment is an optional view of live native floor/area assignments.
Room groups remain distinct from individual locations. Equipment counts use device
records, not their many entities. Entity-only household services retain native area
assignments and a secondary HA reference; no replacement device is created.
Room-level device controls use the same review, signature check and readback as
the exception queues. Entity overrides still require native HA review.

Integration reports expose HA setup errors and repairs with native settings links.
Unavailable equipment, disabled entries, area overrides, shared identifiers and
ambiguous names are review evidence, not permission to remove or merge records.
Connection errors do not establish DHCP/IP drift; deeper diagnosis remains 0.8 work.

Household readiness reads existing evidence through separate admin-only
`GET /api/house/status`. A Music service outage cannot block `/api/house` or room
corrections. The status timestamp identifies the observation; refresh for fresh
evidence. Music requires the existing scoped, expiring audible playback proof.
Calendar/waste verification reuses the saved source selection and 24-hour event
proof. Saved dashboards are ready only within configuration readback scope:
physical display behaviour is still unverified. Climate, cameras, calling, voice,
lighting and appliances never become functionally verified just from reporting.
Unknown/incomplete reads remain unknown; saved deferred choices are respected.

These views are ephemeral projections. The existing private confirmation and
readiness files, permissions, migrations and reset behaviour are unchanged. No
credentials, event contents, camera images or raw presence states are added.

Validation: 347 Python tests and 18 JavaScript tests pass. Desktop light
(1280×900) and mobile dark (390×844) synthetic ingress checks cover people,
floor/room corrections, device placement from both views, physical notes,
combined coverage, save/reload, readiness, evidence outage recovery and calendar
handoff to the existing readiness flow. Full lint/format and privacy gates apply.

Next scope: 0.6 consolidates real household calendar/context, school/sport,
upcoming events, bins/weather and relevant activity context. 0.7 owns physical
display construction and verification. 0.8 owns deeper integration health and
guided repair. Unresolved physical placement and whole-house structure still
require household confirmation; a loaded registry is not a commissioned home.

Release acceptance: implementation commit `dd5237a` passed GitHub CI, including
tests, the app linter and amd64/arm64 image builds. Live deployment is blocked:
Supervisor cannot authenticate to the private source repository during its normal
catalogue refresh. The Green remains on 0.5.3; no update or rollback backup began.
New 0.5.4 views therefore have synthetic browser acceptance only, not live Green
acceptance. Do not describe this as a deployed or fully commissioned release.

The existing Green was read successfully before and after the failed catalogue
refresh and after browser reload. Exact saved screen preferences, existing
Person/structure/placement confirmations and physical notes, device/entity IDs,
Music connection and original playback proof remained unchanged. All saved
dashboard configurations still matched their publication fingerprints; existing
AirTouch sources were reporting. This preservation check does not substitute for
deploying and verifying the new views, or for another audible playback test.
