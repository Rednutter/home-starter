# Household screens — V0.4

Home Starter translates the existing house into native Home Assistant dashboards.
Setup stays in the administrator-only App; household screens use the viewer's HA
account. No frontend projects, custom cards or extra integrations are installed.

## People and places

Versioned `household.json` in the App's backed-up `/data` stores people, physical
screens, preferences, household names/inclusions and explicit activity rules.
Profiles: personal phone, shared tablet, specialist, kitchen, entry, bedside and
non-touch wall. A screen combines a person with a room and physical purpose. These
records do not create users or devices.

## Shared touch shell

Phone, shared tablet and specialist/AirTouch profiles share **House + configured
people** primary tabs. People retain saved list order; stable IDs, not names, own
routes. Encoded person routes cannot collide with contextual routes. There is no
assumed household size and no automatic import or creation of people.

House shows admitted Climate, Today, Home / Rooms and Music sources. Missing
capabilities are omitted. Native buttons expand purpose-specific subviews with a
back path; room views stay contextual. Available quick temperature and playback
controls remain obvious. Safety interruptions appear on every view; opening and
other active-state exceptions retain conditional summaries. The phone dashboard
address and `/home` route remain stable; publication still requires a fresh preview.

Each configured person receives a page with their own Pin/Hide/Reorder preferences.
The physical screen audience is a ceiling, including when viewing an adult's tab.
Children's pages favour rooms explicitly linked through that person's saved screen
records, plus admitted whole-house context. Configure a personal screen's person
and room to establish that link; names are never used to guess bedrooms. Adult
pages may include broader admitted controls. Tabs do not authenticate people or
replace HA account permissions. Household settings are not migrated or rewritten.

The specialist profile prominently shows the main climate control, and admits all
available AirTouch climate/zone/damper entities by registry `platform=airtouch5`,
including unassigned zones. Other local controls still require its configured room.
Tablet and phone use compact climate glances and the same expanded controls.
HVAC modes use advertised `hvac_modes`; temperature uses feature bits 1/2; fan modes
require bit 8 and an advertised list. Native cards own service dispatch and enforce
current capabilities. Missing zone temperature is omitted rather than invented.
Damper positions are informational: an open damper does not establish zone enablement.
Use the zone climate mode for enabled/off status. Automatic temperature control and
the native AirTouch app remain available; no damper service calls are generated.

Today consumes admitted HA calendar entities and their native agenda. Consolidate
external calendars in the chosen provider first; there is no ICS ingestion or
personal event inference. Personal pages use explicitly admitted household context.

## Display lifecycle and device dependency

The supported baseline is **manual native presentation per browser**:

- **Active:** House and personal pages; normal controls and contextual expansion.
- **Ambient:** clock, climate status/current/target, HA next-calendar context and
  playing-media information. No climate or media control widgets.
- **Dark:** black view background with an explicit Wake target. HA chrome and the
  Wake card remain visible; it is not a full black kiosk or physical panel-off mode.

House exposes Ambient and Dark. Ambient exposes Active and Dark; Dark exposes Wake
to House. Native back navigation also returns to House. Safety alerts remain live
and visible in both reduced states. Each browser's route is independent; switching
one screen never changes another. No helpers, global lifecycle automations, guessed
wake commands, idle timers or physical power calls are installed.

Automatic inactivity transitions, household time defaults, brightness/full black,
touch-to-wake while the panel is physically asleep, and future event takeover need
a verified device control path. One concrete option is **Fully Kiosk Browser on the
AirTouch, Remote Administration enabled and its official HA integration**, with
screen control tested on that console. Console Android/browser mode must be inspected on the actual device before enabling
physical wake/sleep or automatic idle. No physical control claim is
made. Installing/configuring device management is a separate explicit device step.

Person preferences follow that person; `surface:<id>` preferences stay with a screen.
Each supports `pin`, `hide` and `order`. Hide wins over pin except for safety signals.
Personal order takes precedence, then physical order, then stable alphabetical order.
Pin never bypasses function, location, audience or diagnostic exclusions. Adult
controls require an adult screen and, if selected, an adult person. Audience choices
arrange screens: they do not change HA account access or create a kiosk boundary.

The setup UI adds people/screens, edits a screen's requirements, assigns household
names, explicitly includes additional actions and saves preferences. Local/floor/
whole_house/personal scope is represented; V0.3 location admission uses local versus
explicitly whole-house scope. Floor/personal refinement and automatic panel discovery
remain future work. This release establishes generation rules, not every final design.

Revision preconditions and atomic file replacement protect settings. Unreadable or
corrupt data is preserved and reported, never reset silently. There is no DB, plugin
engine, usage analytics or network discovery. Preference changes do not rewrite
published dashboards automatically: save, generate, review and publish again.

## Admission and hierarchy

Classification uses HA domains, explicit device classes, registry/device areas,
disabled/hidden flags and diagnostic/config categories. It records area, function,
scope, interaction, importance, frequency, visibility, audience and suitability, with
a reason. Unknown/unavailable sources are excluded, not declared absent forever.
Refresh/regenerate after recovery. Incomplete inventory blocks publication.
An explicitly reviewed scene is an action: its normal never-run timestamp may be
unknown without making the action unavailable. Disabled/hidden/unavailable scenes
remain excluded.

- Level 0: smoke/CO/gas/leak/safety signals, recent doorbell events and informational
  triggered security alarms. Cannot be hidden.
- Level 1: conditional openings, unlocked doors, active media, running climate,
  lights/fans on and vacuum errors. Normal states and their sections disappear.
- Level 2: room controls and explicitly included household actions.
- Level 3: weather, calendar, room temperature/humidity, presence and timers.
- Level 4: room subviews and native detailed controls.
- Level 5: diagnostics, configuration and ambiguous signals stay in administration.

Names alone cannot turn a switch/action/status into a household control. An
administrator must include ambiguous actions and review their effect first. Pinning
or renaming never upgrades battery/config diagnostics. Safety screens do not replace
working certified alarms. Native more-info may show technical detail when opened.

Phone/tablet/specialist use the shared touch hierarchy described above.
Kitchen/bedside: clock, local controls and context.
Entry: access/security, presence and context. Wall: clock, context, exceptions and
activity with no control widgets, actionable taps or room navigation.

Rooms use existing HA areas. Their native navigation buttons and templated summaries
reference only admitted items; hidden controls cannot reappear through automatic
Area-card summaries. Room details are subviews, not extra main tabs.
Unassigned controls are local with unknown location, not assumed whole-house.
Phone/tablet keep them under Other controls unless pinned or explicitly marked
whole-house. Fixed-room screens require a known matching room for local controls.

## Catalogue and native rendering

`surfaces.py` names 25 canonical elements: room summary, quick action, alert, climate
control/summary, light control, media now-playing/favourites, calendar agenda,
clock/weather, weather summary, access, camera, doorbell event, appliance status,
activity today, presence, status chip, timer, notice, security summary, action group,
bedside clock, calling contact and room detail. The catalogue is a capability contract,
not a claim that absent household sources are installed.

Rendering uses native Sections, Tile, Button, Markdown, Thermostat, Media control,
Calendar, Clock and Weather cards. Compact/normal/large are catalogue vocabulary;
native sizing/widget differences are used where meaningful. Camera selection,
favourites, calling/contact, event takeover and recipes/shopping/sport notices need
supported, reviewed sources and are not populated automatically. Calling and media
favourites and camera selection are explicitly `source_required`; no calling platform is installed.

State/template conditions are verified with official Core 2026.10.0. Climate tests
`hvac_action`, not just selected HVAC mode. Doorbell events show for two minutes.
Unavailable states do not become false hazard alarms. Lights/switches use native
toggle; selected actions require native confirmation. Doors/locks/security open native
detail, with no generated one-tap opening, unlocking or disarming. Wall templates
have no service actions.
Critical security interruptions are safety signals on every profile, including
kitchen and bedside screens. Explicit whole-house controls remain suitable on touch
surfaces without admitting ordinary unrelated context; pure action items are not
suitable for a non-touch wall.
Household renaming preserves current inclusion. Enabled critical safety signals stay
included regardless of local name/inclusion/audience overrides; disabled, hidden or
unavailable HA sources still respect their actual source availability.

## Publication and verification

The preview reviews layout/data; it never operates hardware. Native HA evaluates
templates, calendar content and controls. Publication accepts only an exact, recent
server-held preview for the same ingress administrator and settings revision. It
does not accept arbitrary browser-supplied services, dashboard configs or URLs.

HA commands: `lovelace/dashboards/create`, `lovelace/config/save`, and forced
`lovelace/config` readback. Addresses start `home-starter-`, derived from validated
screen IDs. Existing untracked dashboards are protected. Updating requires current
content to match the last published fingerprint; external edits stop the update.
HA has no atomic compare-and-save command: an external edit between check and save
can still race. Writes inside this App are serialized. Renaming changes dashboard
content title; existing sidebar metadata is not rewritten automatically.

Timeout/storage/readback failure stays unverified: a dashboard may be partially
created/saved. Inspect it in HA before retrying. Untracked partial dashboards remain
protected; choose a new screen rather than overwrite blindly. Home Starter does not
delete dashboards or entities. Removing local preferences/activity rules does not
remove published dashboards or synthetic sensors; handle that later in deliberate
HA administration.

## Appliance activity today

Choose an existing status and its documented running → completed transition. No
appliance-name guesses, inferred human completion or chores. Tracking starts when
the background monitor first loads a saved rule (within 30 seconds, or immediately
on generation). An already-running source can form the initial baseline; only a
later explicit completion counts. Changing the source/transition resets tracking.

The monitor reads recorder history every 30 seconds, including short cycles between
polls. It persists the consumed timestamp before publishing, preventing double counts
from overlaps/restarts. Unknown/unavailable breaks continuity. `last_run`, `runs_today`
and `ran_today` persist locally; daily count rolls in HA's timezone, including DST,
within one poll of midnight. Missing/excluded recorder history reports unknown.

Only virtual `sensor.home_starter_activity_<hash>` states are written through HA's
REST state API. Existing states without the matching ownership marker are protected.
They are not registry devices/helpers; Core restart may remove them, and the App
recreates them from its persistent records. Generated cards update from those sensors
without republishing. Tracking never calls an appliance service. Retention, recorder
exclusions, delayed history and outages limit coverage: counts describe retained
observed transitions since tracking began, not lifetime activity or guaranteed coverage
during missing-history intervals.

## Acceptance

Tests cover seven profiles, safety/audience/location boundaries, hidden diagnostics,
precise native targets, stale settings/publication, failed readback, persistent count
deduplication and Sydney day rollover. `devtools/v3_core_config.yaml` is for a disposable
official Core only: simulated lamp, thermostat and washer. `e2e_surfaces.py` exercises
setup/publication; `e2e_native_surfaces.py` checks loaded cards and climate control;
`verify_v3_activity.py` checks two real recorder completion transitions. Private test
credentials, runtime records and screenshots remain ignored under `screens/`.

`tests/test_touch.py` additionally covers 0–50 people, stable ordering, adversarial
route IDs, child room context, physical audience ceilings, capability gating and
manual lifecycle navigation/safety. `devtools/v3_harness.py --fixtures` with
`devtools/e2e_touch.py` checks populated administration and publication/readback
against contract fixtures; it does **not** verify native HA rendering or hardware.
The disposable-Core/native harness requires a working Linux Docker engine.
Official Supervisor schemas require Linux (`fcntl`); the App linter runs on Windows.
Record real Green acceptance separately in private runtime storage.
