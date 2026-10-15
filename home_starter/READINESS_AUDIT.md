# Household evidence and setup audit

## 0.6.1 Physical screens

Saved dashboard readiness still means publication/readback. A separate physical
screen readiness row requires current dedicated-account evidence, two native
caller checks and an explicit physical-use report. Missing account inspection,
changed bindings and unverified restart/physical use remain unfinished.
See [supported mechanisms and acceptance](SCREEN_COMMISSIONING.md).

## 0.6.0 Household Context

Readiness version 2 adds explicit dated morning rules and occurrence-bound event
preferences. Version 1 is migrated in memory without rewriting on inspection;
prior source decisions and proofs survive. Current source identity, the existing
24-hour verification lifetime and per-display admission still gate calendar/waste
context. A running background refresh is not renewed household verification.
Only explicit wall publication enables its expiring native HA state projection.
See [schema, privacy, migration and acceptance](HOUSEHOLD_CONTEXT.md).

Audit baseline: 0.4.2, 14 October 2026. Product source, catalogue, generators,
migrations, fixture provenance and all 49 local screenshot files were inspected
(48 distinct images). Screenshot bytes, private names, entity IDs and calendar
contents remain outside Git. The public report identifies product rules, not the
developer household. No screenshot or template is used as household configuration.

## Findings and changes

There was **no hard-coded Bins feature or seeded collection schedule**. Calendar
entities were automatically classified as household context; the generator then
showed available calendars on eligible screens. A real household waste calendar
therefore appeared in an old phone capture. Availability was not proof of a useful
collection event, and the household had not chosen its displays.

Unjustified defaults found:

1. Every available calendar was eligible without a chosen consolidated source,
   event read or display selection. This included possible waste calendars.
2. Every available HA person could appear, without establishing that the identity
   represented a household member or that presence belonged on that display.
3. Explicit appliance rules produced counts on every fixed-screen profile,
   regardless of the appliance's room.
4. Music Assistant's installed/running/connected status could be read as whole-home
   Music completion, even though providers, accounts, groups and playback were unknown.
5. The optional preparation/extras lists were the only broad interview. They did
   not persist household intent, deferral or readiness across these capabilities.

The new interview also excludes HA demo-platform entities, does not treat the
built-in conversation component as a voice device, and does not infer a Music
Assistant installation from a failed check. Stopped/unavailable Music Assistant
states remain visible after a household records its music intentions.

New previews default to no calendars/waste/presence. Calendar/waste admission
requires a saved wanted decision, real source, selected displays and a successful
dated upcoming-event read. A waste source needs an identifiable collection event
or a recognised waste-service platform; a name match is merely a suggestion.
Verification expires after 24 hours and is invalidated by selection, registry
identity or advertised connection changes. Event titles/payloads are not persisted.
Empty, stale, malformed, unavailable and unrelated events cannot verify Bins.

Presence requires explicit member/source links and display selection. Optional
capability opt-outs and selected source/display restrictions are honoured. Ignored
or hidden devices lose normal controls; safety interruptions remain visible.
Fixed-screen appliance counts require the matching source room, and an optional
appliance display decision is respected. Child context can reduce an existing
adult content audience; it never grants access or changes HA users.

Existing dashboards and 0.4.2 settings are retained. **These rules apply to new
previews and explicit reviewed publications**, not an automatic rewrite of installed
dashboards. Review old calendar/presence content in Home Readiness and republish
each chosen screen when ready. Publication ownership/external-edit protection,
matching-config no-op, reset confirmation, migration and inventory history remain.

## Automatic content inventory

“Working” below distinguishes current HA availability from end-to-end verification.
Pinning does not override source admission, suitability or audience boundaries.

| Item | Trigger/evidence and data source | Working check | Asked/decision | No valid source |
|---|---|---|---|---|
| Bins/waste | Explicit selected HA calendar; actual collection event/service | Authenticated upcoming-event GET; dated event, source identity/connection and 24h proof | Wanted + source + displays; no default schedule | Hidden in new previews |
| General calendars/Today | Chosen consolidated HA calendar | Actual upcoming-event read, not `off` state or cached message | Explicit source/display selection | Hidden; readiness links to HA calendar setup |
| Presence | Available HA person/tracker linked to a saved household member | Current state availability; purpose is a plan, no automation verified | Member link, purpose and displays | Hidden; no guest/account assumptions |
| Rooms | HA area containing admitted sources | Available admitted sources; no inferred room assignment | Screen room and Pin/Hide/Reorder; unresolved device requires assign/hide/ignore | Empty room omitted |
| Lights | Native HA light, not diagnostic/disabled/hidden | Available state + advertised controls; operation is not verified by discovery | Existing HA evidence by default; optional source/display decision and opt-out | Hidden |
| Climate/fans | Native HA climate/fan; AirTouch platform-specific damper semantics | State and supported features/modes; connection drift surfaced separately; no automatic physical test | Screen role/room; optional source/display decision; test in HA | Hidden; never invent modes/zone temperatures |
| Weather | Native HA weather entity | Available known state; forecast/provider accuracy not proven | Existing HA source; Pin/Hide available | Hidden |
| Media | Native HA media player | Available state; provider/playback not proven | Optional Music sources/displays, providers/account/group intentions | Hidden; no assumed Spotify/favourites |
| Music setup prompt | Speakers or installed MA, or explicit wanted decision | MA app/connection checks separate from provider/playback verification | Conditional provider/account/group questions; secure setup in MA | No unsolicited provider question in minimal homes |
| Appliance/vacuum status | Native vacuum, or explicitly included household action | Available state; completion never guessed from appliance name | Optional appliance display/source choice | Hidden |
| Activity today | Saved documented transition + observed recorder history + owned virtual sensor | Recorder intervals, ownership, deduplication; gaps stay unknown | Explicit rule; fixed-display room relevance and optional display choice | No invented count or chore assertion |
| Chores | No implementation/source | None | Not offered as a completed capability | No card/automation |
| Cameras/recording/intercom | Discovery in readiness only; catalogue remains source-required | Entity does not establish live view/events/recording/intercom | Check each in HA; support/verification remain incomplete | No guessed camera/recording card |
| Doorbell alert | HA event with `device_class=doorbell` | Current event/time; bounded display condition | Existing typed HA evidence; no calling/intercom enabled | No event alert without source |
| Opening/security alarm | HA opening/alarm types, not label guesses | Conditional active/triggered state; adult controls retain ceilings | Actual HA evidence; informational interruption is mandatory safety | Absent without source |
| Smoke/leak/gas/safety | Typed HA safety binary sensor | Abnormal-state conditional | Cannot be hidden by preference/device decision | Absent without source |
| Calling/communications | Explicit interest or known SIP/VoIP integration | **No registration/call verifier**; never marked working | Service, internal/external/gate intent, per-person destinations; Not now/not wanted | No calling card, extension, permission or installation |
| Voice | Assist satellite/assistant integration or explicit interest | **No end-to-end voice verifier** | Keep/remove/replace and controls; room/service setup handoff | No invented assistant or automation |
| Power switches/scenes/scripts | Explicit administrator inclusion only | State available; service effect not automatically tested | Include plus audience/scope; unsafe technical controls stay excluded | Hidden unless explicitly admitted |
| Temperature/humidity/timers | Typed native HA measurement/timer | Available known state; diagnostics excluded | Existing HA context + applicable profile; preferences | Hidden |
| Clock/Display/Ambient/Dark/Wake | User-selected screen profile and native HA clock/navigation | Native UI; manual mode only, no physical wake/sleep claim | Explicit physical role/profile | Structural UI only; no invented household data |
| Notices/action groups | Admitted exceptions or explicitly included actions | Native source conditions | Real source/decision required; no canned household notice | No invented notice |
| Energy/solar/EV/transport/commute/irrigation | No automatic household semantics for ambiguous sensors | Not claimed supported | Only explicit generic action inclusion where appropriate | No template card/recommendation/automation |
| Inventory findings | Registry/state/config-entry evidence | Bounded read, confidence and explicit room-change readback | Review before mutation; assign/hide/ignore unresolved devices | Incomplete scans preserve history |
| Preparation/extras | Optional generic physical checklist, not a discovered capability | Not verification | Explicit checklist/review; extras remain page-local possibilities | Never configures/installs from a checkbox |

Generated admitted items now carry their HA entity/registry/device/platform evidence
and admission reason. Native structural cards trace to the selected profile,
admitted room sources, saved people, explicit activity rule or navigation target.
The catalogue describes possible native widgets; `source_required` entries are not
rendered simply because they are in it. Diagnostics remain administration-only.

## Missing interview/flow coverage

| Area | 0.4.2 gap | Implemented decision/revisit path | Still incomplete |
|---|---|---|---|
| Household | Names/audience only; no explicit adult/child context, rooms/devices/access intent | Saved member context alongside saved people; child content ceiling | HA account creation/access verification; no users created here |
| Music | Installer/HA connection only | Conditional providers, shared/individual/mixed accounts, room sources/displays and group intent; MA handoff | Provider discovery/configuration, exact groups and actual playback verification |
| Communications | Source-required catalogue only | Conditional SIP/service and separate internal/external/gate plan; each person's destinations default empty; explicit deferral | Secure service adapter, extensions, enforced permissions, registration, actual internal test call, endpoint monitoring |
| Calendar/waste | All available calendars admitted | Chosen source/displays, real event read, revisit on failures/drift/expired proof | External-source connection happens in HA; manual schedules are not created here |
| Displays | Profiles already establish role; no physical discovery guarantee | Configured count + explicit shared/personal, room and interactive/wall roles | Discovering physical browser/display agents; physical lifecycle control |
| Voice | No interview | Conditional keep/remove/replace and allowed-control intentions; HA handoff | Room setup, actual assistant tests and enforced permissions |
| Presence | All HA people considered household context | Actual member/device/source links, intended purpose, display choice | Presence-driven automation/control testing |
| Climate/lighting | Available state/capability gates; no setup test contract | Source/role decision, room resolution, drift/revisit and truthful control-test requirement | Automated safe control test/readback; available is not “verified working” |
| Appliances | Explicit transitions, but broad display admission | Existing simple rules retained; room/display relevance | Arbitrary appliance discovery, lifetime counts or chores |
| Cameras/doorbells | Unsupported camera/intercom semantics | Conditional per-capability questions and HA route | Stream/event/recording/intercom verification adapters |

Home Readiness stores versioned private decisions separately from the 0.4.2
household model. GET performs no HA writes. Save only records plans; supported
verification only reads calendars. Reset changes epoch, invalidates readiness and
retains a private recovery copy. Corrupt/future state fails closed. Pending choices
survive refresh errors; stale saves/previews fail instead of overwriting.

## Screenshot/view audit

All archived screenshots are evidence of their own version/fixture, not approved
defaults for another home. Full private file/hash inventory is in ignored
`screens/content-audit/manifest.json`; the groups below cover all 49 inputs.

| Screenshot/view group | Visible items | Source/trigger | Justified? / fix | Relevant regression |
|---|---|---|---|---|
| `green-v3-phone.png` | Quick action, rooms, waste calendar, weather, person, overflow controls | Actual HA entities and explicit screen/preferences | Controls/rooms/weather have real sources. Calendar/person exposure lacked display/member selection; gate future previews. Private identities stay out of this report | Fresh-profile Bins omission; verified source/display; member links |
| `green-phone-published.png` | MA connection status, saved person/screen, publication result | Existing app/integration and saved settings/readback | Yes within scope; app connection is not provider/playback completion | Rerun/publication regression; unsupported verification test |
| `green-0.4.2-installed.png`, `green-0.4.2-version-proof.png`, `green-v032-installed.png`, `green-v033-installed.png` | Version/changelog/App controls; host chrome | Supervisor App UI | Version evidence only. Host/sidebar content is not product seed data | App validation and installed-version acceptance |
| `v3-ui/native-phone-{desktop,mobile}.png` | Light, room/temperature, family calendar, explicit washer count | Disposable Core light/calendar/sensor + saved rule/profile | Controls/count provenance yes; unverified calendar needs gating | Calendar consent/verification; existing activity tests |
| `v3-ui/native-{specialist,tablet,wall}-desktop.png` | Climate, room, calendar where applicable, count; wall clock | Disposable sources/profile and explicit rule | Climate/room/clock yes. Calendar selection missing. Fixed-display activity needs matching room | Seven fresh profiles; source/display consent; fixed-room activity |
| `v3-ui/setup-{desktop,mobile,phone-desktop,phone-mobile,specialist-desktop,tablet-desktop,wall-desktop}.png` | People/screens/preferences, preview/publication; source blocks above | Saved synthetic people/profiles and disposable sources | Administration justified. These previews are not native/source verification; obsolete calendar defaults are superseded | Preview expiry/ownership; new readiness source tests |
| `v4-ui/setup-{phone,specialist,tablet}-{desktop,mobile}.png` | House/person tabs, climate, Today, rooms, display modes | Fixture entities + explicitly saved synthetic people/profiles | Structural/navigation/climate justified. Today depended on an unreviewed fixture calendar; now absent until verified/selected | Touch navigation regression; no template calendar admission |
| `inventory-ui/{desktop,mobile}-{final,preparation,review,verified}.png` | Optional checklist, inventory findings, room-change review/readback, system details | Synthetic inventory + explicit room-change action | Yes as admin evidence. Checklist is not installation/configuration proof | Inventory browser regression, unresolved assign/hide/ignore |
| `inventory-ma-regression/01-scan.png`, `02-music-available.png`, `03-confirm.png`, `04-installing.png`, `05-discovered.png`, `06-ready.png`, `07-open-music-assistant.png` | Scan, optional outcome, installer stages, HA handoff | Synthetic Supervisor/MA/Core contract states and confirmation | Installer stages justified; “ready” only meant app/HA connection. Provider setup remains incomplete | Existing Music E2E; conditional provider questions |
| `v4-music-e2e/01-scan.png`, `02-music-available.png`, `03-confirm.png`, `04-installing.png`, `05-discovered.png`, `06-ready.png`, `07-open-music-assistant.png` | Same installer sequence plus household editor | Same synthetic contract states | Same limits; open-MA capture is a navigation stand-in, not actual playback | Music E2E and five household scenarios |
| `rerun-ui/existing-{desktop,mobile}.png`, `review-error.png` | Saved counts/publication, climate availability, Music status, differences, error retry | Synthetic saved state/current inventory and injected conflict | Yes for saved-state/retry behavior. Availability/app state must not imply end-to-end readiness | Rerun E2E and error retry |

New synthetic captures under `screens/readiness-ui/` supersede these onboarding
assumptions: persistent readiness, conditional questions, deferrals and verified
calendar/display selection. No private screenshot is promoted into fixtures or Git.

## Scenario acceptance

`tests/test_readiness.py` constructs five deliberately fictional households:

- Complex family: two adults/three children, several rooms, Green/MA, Google audio,
  AirTouch/Shelly, wall/tablet/phone, cameras/doorbell and calendar. Providers are asked
  about, Spotify only appears after an explicit answer, and no waste is presumed.
- Apartment: two adults, lights/Google assistant/audio. Music/voice questions appear;
  no SIP or waste questions appear without interest/source evidence.
- Fresh family: two adults/two children, mixed device integrations. Household/room
  context is unresolved; Music/SIP/waste questions are omitted.
- Enthusiast: local-media intent, SIP/PBX, cameras/Zigbee/ESPHome. Calling requires
  choices but stays incomplete; explicit Not now is persisted. No call is enabled.
- Minimal: one adult and a light. No Music/voice/SIP/waste interview is inferred.

Each checks discovered sources, asked/omitted questions, persisted choices, no HA
configuration from plans, unresolved state, irrelevant content omission and honest
verification. Additional tests cover all seven fresh profiles, real/invalid/stale
collection events, identity drift, consent/display gating, child call/audience
boundaries, opt-out with mandatory safety, reset/restart and private API guards.
The fixture browser flow tests the actual interview, save/reload, explicit deferral,
source verification and fresh preview, in addition to the existing rerun/Music/touch
flows. Fixtures prove contract behavior; they do not establish physical operation.
