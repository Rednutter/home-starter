# This House

Home Assistant owns people, trackers, floors, areas, devices and entities. This
House reads those records live. It does not maintain a second household registry.
Existing screen profiles remain saved display preferences, distinct from HA people.

Confirm existing Person records as adult, child or display/other account, and
compare their assigned trackers. Roles affect the commissioning count only, never
HA login permissions. Tracker ownership and pairing use native Person settings.
Reporting presence is not proof of ownership or reliable presence detection.

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
