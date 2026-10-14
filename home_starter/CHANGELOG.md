# Changelog

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
