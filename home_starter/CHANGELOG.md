# Changelog

## 0.8.3

- Add explicit kiosk presentation for specialist panels with a suitable dedicated
  non-admin display account and installed official HACS Kiosk Mode module.
- Fill the overview without HA chrome for that account only. Keep native Back
  navigation on control pages and a visible Settings escape that restores HA
  navigation; Panel mode returns to the overview. Admin navigation stays visible.
- Preserve existing screen choices by default. Require fresh reviewed publication
  and recheck frontend dependencies before any dashboard write.
- Verify account scope, settings exit/reentry, reload and native controls using
  disposable HA with Kiosk Mode 15.0.0. Retain readable narrow navigation labels.

## 0.8.2

- Apply compact landscape spacing at the actual 720px-high display size so
  Media/Home detail text remains visible. Add that viewport and tile-copy bounds
  to native acceptance.

## 0.8.1

- Bound the selected weather icon inside the landscape header. This prevents
  button-card's inherited icon sizing from compressing the household panels.
- Include selected weather and header bounds in disposable native acceptance.

## 0.8.0

- Restore a reference-led specialist landscape overview with prominent Climate,
  household context and configured people navigation. Retain native control
  subviews, permissions and existing household choices.
- Use an installed official HACS button-card module as the optional visual shell;
  detect it through supported resources APIs and recheck before publication.
  Missing dependencies retain the native fallback without dashboard writes.
- Keep unavailable climate, selected mode versus live activity, missing services
  and expired bin evidence explicit. No invented temperatures or commissioning.
- Preserve dashboard ownership/readback and explicit publication. Other screens
  are unchanged. Add focused tests and disposable native non-admin acceptance.
  See [the panel contract and verification limits](AIRTOUCH_PANEL.md).

## 0.7.1

- Keep verified Council-service readiness authoritative over legacy calendar
  discovery and preserve the direct Waste collection setup link. This fixes a
  summary mismatch found during confirmed live-household commissioning.

## 0.7.0

- Add Council-backed waste collection as household context, with Wodonga's
  locally matched collection areas and dated official annual calendar.
- Confirm service, selected screens and six native bin/status helpers explicitly.
  Keep address coordinates out of saved waste state and Council requests.
- Show bins only from the prior evening until the Council's morning deadline;
  retain labelled last-valid evidence during outages and stop expired patterns.
- Preserve existing settings, publications and legacy calendar choices. No
  synthetic events, automations or automatic dashboard republication.
- Add focused source, migration, privacy, context and native HA/browser checks.
  See [Waste Collection](WASTE_COLLECTION.md) for evidence and boundaries.

## 0.6.2

- Reuse an existing dedicated display account linked to a currently reviewed
  display/other Person, preserving its native tracker assignments. A device
  tracker does not make a display a household member. Household-member accounts,
  stale confirmations and ambiguous Person links remain protected.
- This correction follows live inspection after 0.6.1 deployment; no native
  Person records, trackers or credentials were changed to satisfy eligibility.

## 0.6.1

- Separate fixed/shared screen publication from dedicated HA account, session,
  restart and physical-use commissioning. Keep existing dashboards and settings.
- Inspect native accounts and guide native credential setup; explicitly prepare
  suitable existing display accounts through supported local-only/read-only APIs.
- Verify the native caller with an owned button helper and separate check page.
  Keep physical use and restart method as explicit owner reports, not inferred facts.
- Store only private, versioned commissioning evidence. Preserve all 0.6.0 files;
  an existing published screen begins with its display identity unverified.
- Add focused lifecycle tests and disposable native HA acceptance, including
  non-admin climate controls, default dashboard and browser restart persistence.
  See [scope, privacy and remaining physical steps](SCREEN_COMMISSIONING.md).

## 0.6.0

- Add Household Context using the chosen verified HA calendar, explicit dated
  morning rules and conservative departure preferences. Preserve existing
  Readiness choices through a lazy version 1 to 2 migration.
- Add a compact adaptive native wall: current commitments and a longer upcoming
  horizon when quiet. Elapsed scheduled events leave the display without a claim
  of completion. Missing/stale evidence remains explicit.
- Update only explicitly published walls through owned, expiring HA state with
  native readback. Respect screen/source exclusions, external dashboard edits and
  reset/publication boundaries. Disclose HA recorder exposure before publication.
- Preserve Music, This House, saved screen preferences and other native profiles.
  Correct the commissioning handoff into the collapsed Home Readiness section.
- See [acceptance and deployment limits](HOUSEHOLD_CONTEXT.md); disposable native
  HA success does not establish Green deployment or household operation.

## 0.5.4

- Inspect live equipment and entity-only services by their native HA floor/area,
  with the same reviewed device placement controls and no copied registry.
- Surface HA integration setup reports and native repair handoffs, keeping
  connection failures distinct from an unproven cause such as changed IP addresses.
- Add read-only household readiness using existing Music playback, calendar event
  and saved-dashboard readback evidence. Reporting climate/cameras remain partially
  ready; installation alone never proves operation. Evidence failures do not block
  house inspection or corrections.
- Preserve existing private choices, confirmations, Music credentials/proof and
  dashboard publications. No persisted schema or migration changes.

## 0.5.3

- Record optional presence intent against an existing HA Person. Intentionally
  untracked members are accepted separately from missing/unavailable trackers,
  without inferring home/away or changing native Person/tracker records.

## 0.5.2

- Confirm equipment that serves several rooms using a required physical coverage
  note, without inventing a single room or changing HA assignments. Keep a wall
  controller's physical placement separate from the zone it controls.
- Preserve existing confirmations when these optional intent fields are added.

## 0.5.1

- Show integration provenance and flag same-named equipment records for review,
  keeping valid views of the same hardware separate without proposing deletion.
- Keep earlier capability-planning choices under Review setup and explain their
  screen-profile context, distinct from live This House and Music verification.
- Use plain confirmation labels for household size and area purpose.

## 0.5.0

- Add This House: live HA people, trackers, floors, areas and physical equipment,
  with discrepancies first and optional inspection of already placed devices.
- Review and write floor, area and device placement changes through supported HA
  registry APIs, with stale-change checks and readback before confirmation.
- Retain private household roles, area grouping intent, portable-equipment intent
  and short physical notes without duplicating HA's registry. Native changes reopen
  affected confirmations. Keep screen preferences distinct from HA Person records.
- Preserve existing Music checks, published dashboards and saved screen settings.

## 0.4.8

- Distinguish audible confirmation from automatic progress evidence for speakers
  with infrequent status updates. Require an attributed, active source/queue/player
  path and human confirmation; disclose when automatic progress remains unverified.

## 0.4.7

- Wait briefly for a chosen speaker to start or finish buffering before observing
  advancing playback. Keep authentication, source attribution and hearing checks.

## 0.4.6

- Explain which playback evidence is missing instead of issuing a generic retry.
  Preserve strict verification and all existing service settings.

## 0.4.5

- Recognise actual MA music providers separately from plugins and built-in URLs;
  guide missing source setup without changing existing provider accounts.
- Add a private, explicitly connected MA API credential with safe replacement.
- Observe fresh playback from a chosen provider and speaker, then require audible
  confirmation. Scope and expire proof; never complete Music from installation.
- Preserve provider settings, queues, groups, volume and household dashboards.

## 0.4.4

- Separate first-run commissioning from returning-home maintenance.
- Persist a resumable household/capability draft, explicit consolidated review and
  Set up my home action before automatic configuration/publication.
- Preserve existing dashboards by default; update only explicitly selected screens.
- Journal independent execution results, supported checks and deliberate skips;
  recover interrupted work without replaying successful publications.
- Add six flow scenarios and document actual 0.4.2 behavior and remaining service tests.

## 0.4.3

- Add persistent Home Readiness and conditional household/source/display decisions.
- Require selected, verified calendar/waste sources and chosen displays. Link presence
  to actual household members; never assume Spotify or enable SIP from discovery.
- Keep unsupported provider/playback, calling, camera and physical control tests
  visibly incomplete. Record explicit Not now/not wanted decisions.
- Respect opt-outs, ignored devices, child audience ceilings and appliance room
  relevance while preserving safety interruptions and existing published dashboards.
- Audit default content, setup gaps and archived examples; add five synthetic
  household scenarios and source/decision provenance. See READINESS_AUDIT.md.

## 0.4.2

- Resume explicit versioned setup on subsequent visits. Preserve people, screens,
  preferences and activity rules; migrate existing settings once without resetting.
- Show House status and inventory differences without rebuilding HA resources.
  Recognise registry renames and connection/capability changes for explicit review.
- Skip dashboard writes when the published configuration already matches. Preserve
  external-edit protection and require typed confirmation to reset local setup.
- Keep runtime state outside source/package files, redact secrets in logs, and gate
  Git content with reviewed synthetic secret fixtures plus manual privacy inspection.
- Replace private acceptance notes and identifying metadata with public examples;
  sanitise affected Git history. No live credential was identified in the audit.

## 0.4.1

- Put the main system thermostat before zone/damper controls in expanded Climate.
  This preserves first-class climate emphasis when zone names sort earlier.
- Live Green acceptance of 0.4.0 verified publication/readback, native House/person
  navigation, room details, manual display views, main target adjustment and one-zone
  off/on control with restoration. See [acceptance evidence](ACCEPTANCE.md).

## 0.4.0

- Phone, tablet and AirTouch/specialist now share House + saved people navigation,
  with stable ordering and collision-free contextual routes. Rooms, climate,
  calendar and music expand into native subviews; absent capabilities are omitted.
- AirTouch climate is prominent. Registry-platform admission includes all available
  zones; temperature/HVAC/fan controls use advertised capabilities. Damper position
  is informational. Unknown zone temperatures are not invented.
- Personal pages retain person preferences within the physical audience ceiling;
  child context uses explicitly linked screen rooms. Safety stays visible on every
  view and conditional opening exceptions retain their prominent summary.
- Manual Active/Ambient/Dark presentation is per browser. Ambient shows live context;
  Dark uses a black background with a Wake target and HA chrome. Automatic idle,
  brightness/full black and physical wake/sleep require verified device management,
  such as Fully Kiosk Remote Administration plus its HA integration.
- Existing settings, phone addresses, inventory, Music Assistant, explicit appliance
  activity and preview/publication/readback protections remain in place.
- Added shared-shell regression coverage and populated fixture ingress acceptance.
  Native/device acceptance evidence and environment limits are recorded separately;
  fixtures do not establish live control verification.

## 0.3.3

- Critical security interruptions are informational safety alerts on every profile,
  including kitchen and bedside screens, without exposing normal alarm controls.
- Explicitly reviewed whole-house actions remain suitable for specialist panels;
  pure action items stay out of wall displays. Catalogue descriptors now match
  the implemented room summary and deferred camera support.
- Household renaming preserves existing inclusion. Safety source availability
  is separate from control inclusion, so names or audience overrides cannot
  accidentally hide an enabled critical interruption.
- Reviewed scenes that have never been run remain usable; their normal unknown
  activation timestamp is not treated as an unavailable control.

## 0.3.2

- Fix first-use person/screen/activity creation on HTTP Home Assistant ingress.
  Generate record IDs with `crypto.getRandomValues`; `randomUUID` requires HTTPS.

## 0.3.1

- A missing room no longer implies whole-house scope. Unassigned controls remain
  deliberately reachable under Other controls, or can be pinned on a phone/tablet.
- Fixed-room screens exclude controls whose local position is unknown, unless
  explicitly given whole-house scope. Safety interruptions retain precedence.
- Shared-screen security interruptions stay informational and conditional;
  exception-only content does not create empty main navigation tabs.

## 0.3.0

- Make the house usable: people, seven screen profiles, semantic admission,
  a 25-element capability catalogue, native Sections generation and room detail.
- Separate personal and physical-screen Pin / Hide / Reorder settings, stored
  locally in the App's backed-up `/data` directory.
- Administrator-reviewed dashboard creation/update with exact preview tokens,
  readback verification and protection for dashboards edited outside Home Starter.
- Explicit appliance completion transitions from HA recorder history; persistent
  last_run / runs_today / ran_today, daily rollover in HA's timezone and live
  Home Starter activity sensors. Missing history remains unknown.
- No dashboard projects, HA accounts, cloud analytics, inferred chores, calling
  service, entity removal or changes to existing inventory/MA flows.

## 0.2.0

- Fresh Batteries: optional household preparation and rescan at any time.
- Your home: rooms, floors, devices, entity relationships and conservative,
  explainable findings from supported Home Assistant registry APIs.
- Explicit administrator-only device room assignment with precondition checking
  and a fresh registry read to verify the result. No rename, merge or deletion.
- Lightweight reminders for hardware HA may not know about; choices are not saved.
- Music Assistant behavior and App permissions remain unchanged.

## 0.1.1

- Require an active Home Assistant administrator for setup operations.
- Verify the MA ingress listener, matching server version and completed
  onboarding; keep missing or ambiguous evidence unverified.
- Preserve unknown app/compatibility states on API failures, redact reflected
  tokens before error logging, and reject HTTP errors with success-shaped bodies.
- Restore UI controls after setup settles and reconfirm installation retries.
- Add adversarial regression tests for these cases.

## 0.1.0

- First version: read-only Home Assistant scan, and the "Music around the
  house" outcome that detects, installs/starts or hands off to Music Assistant,
  verifies it and opens it.
