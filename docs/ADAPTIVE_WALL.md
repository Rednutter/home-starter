# Kitchen Wall presentation

The Pi keeps its existing native HA dashboard, dedicated restricted account,
Chromium kiosk profile, systemd services, health endpoint and 180-degree output.
This is a passive shared board, not an enlarged AirTouch control surface.

## Data and composition

`context_runtime.inspect` reads the existing verified consolidated calendar,
explicit event/person/departure links and selected household sources. It calls
`wall_composer.compose`; its `wall` output is reusable by other presentations.
No title keyword infers school, a holiday, a destination or a travel estimate.
People use explicit event links or confirmed calendar ownership. A unique leading
confirmed-person label such as `Example · Gym` is also explicit attribution;
arbitrary mentions or ambiguous names never assign a person. Unassigned events
stay household commitments. This projection does not rewrite calendars/settings.

The composer exposes `day_state`, `baseline_state`, `primary`, `next_movement`,
`today_items`, `future_attention`, `household_exception`, `active_context`,
`display_session`, `spans` and `valid_until`. Named states are busy morning,
quiet daytime, pre-activity, active movement, evening, overnight, weekend,
abnormal schedule and exception. Urgent context overrides the clock baseline.
The supplied weekday mock-up is the canonical visual composition: a large
clock/date and weather hero, three circular-avatar person cards, right-hand
timeline, lower-right Later/Week ahead panel, and a readable household/status
bar. Keep the photographic background visible through lighter tinted glass;
do not replace the cards with floating text or a wide school table. Native
permitted portraits are used where present, otherwise clean initial circles.
Rose/blue/green accents distinguish people without solid-colour cards.
Evening selects tomorrow's people, confirmed requirements and forecast. Sunday
afternoon also brings Monday forward. Imminent commitments override preview.
Monday naturally returns to Today using the same person keys and placement.
No generic "Next movement" panel. Ordinary selected events are eligible for seven days;
later events require explicit preparation/holiday/early-attention annotations,
up to 21 days. Nonempty days are grouped, including a combined weekend. Capacity
is shared across days before extra rows from one busy day are added. Locations
are short venue labels rather than postal addresses.
The 21-inch wall is a glance surface. Content capacity accounts for people,
departures and longer titles. Reduce secondary rows before reducing legibility;
empty groups disappear and neighbours expand. Remaining tonight is secondary to
tomorrow unless imminent. Night suppresses secondary information and density.

`static/wall-content.js` renders these priorities and applies only freshness,
expiry and viewport-capacity checks. `static/wall-layout.css` restores the approved
landscape, card composition and stable anchors with lighter glass. Native composition changes
crossfade for 450ms when supported, respecting reduced motion. Poll/clock updates
do not animate continuously. Stale/foreign data clears immediately without a fade.
Evening shows known early starts/departures and confirmed next-day routine rules;
explicit changed-routine dates/holidays suppress routine preparation. No invented
kit, travel or forecast claims. Household status reads only selected native
sources. Unknown is never "All good". Camera thumbnails require verified selected
sources and their own native HA proxy; no stock footage. Active timers/media
share the camera/status region. Safety exceptions outrank sessions.

Current temperature and the focused day's low/high/condition come from the selected source's
native [daily forecast action](https://www.home-assistant.io/actions/weather.get_forecasts/).
Forecast reads are cached only in process memory; evening prioritises tomorrow,
with current conditions secondary. Missing highs are labelled
unavailable. Native person portraits are used only when a selected Person source
provides a permitted local image path; otherwise initials appear.

## Editable household choices

In **Household Context**, use **Adaptive wall timing and routine exceptions**
for the baseline hours, departure thresholds, horizon, temperature thresholds
and dates without normal morning routines. These are optional `context.wall`
settings in the existing readiness store, not schedules embedded in components.

Link a calendar event to confirmed HA people and its known travel/margin/routine.
For school, explicitly retain the useful **08:30** routine on the event link;
no real event is invented before a calendar is connected. Departures always round
earlier to the configured five/ten-minute boundary. All-day events can be linked
as **Holiday / changed routine**, suppressing the normal morning rules. Select
**Preparation needed** or **Show this event early** for travel/planning items.

Weather is current selected HA evidence. A rain/temperature consequence is
promoted around an actual movement. Forecast-at-departure claims are not made
without a forecast source. Bins reuse the confirmed existing waste engine;
collection days/alternation are not guessed or duplicated in the wall composer.

## Temporary display sessions

Authenticated administrator ingress routes:

- `GET /api/wall/{surface}`: inspect the current composer output.
- `POST /api/wall/{surface}/session`: send `{ "epoch": <current epoch>,
  "session": { "kind": "answer", "title": "...", "body": "...", "seconds": 120 } }`.
- Send `session: null` to close immediately.

Kinds: recipe, camera, weather, plan, answer, timer and departure. Text is escaped,
limited to 600 characters/eight newlines (camera captions 160); durations are
5–600 seconds. No arbitrary URLs/HTML or navigation. The board stays underneath,
continues recomposing and is restored at expiry. Sessions live only in process
memory and are discarded on epoch change/restart/expiry. Publication must still
match its owned fingerprint before any projection update.

**Privacy:** displayed context is projected to HA state and may be retained by HA
Recorder, just like the existing explicitly published household context. Do not
send private transcripts, credentials or material inappropriate for a shared wall.
There is no automatic copying of Assist transcripts. A deliberate Assist/automation
caller can use this contract; a native voice-to-visual action is not commissioned
until that caller is configured and tested. Provider credentials stay native.

Camera sessions require a real camera chosen for that wall in Home Readiness and
a fresh native snapshot-response check. This is not proof of recordings, motion,
intercom or the wall account's permission. The browser uses the named native HA
camera proxy; HA still enforces its account access. Verify that actual account on
the physical display before relying on a camera. **Temporary doorbell camera** in
Household Context pairs explicitly selected events/cameras. Doorbell takeovers
expire after two minutes; no permanent feed is added. Missing cameras show an
unavailable state, never stock imagery masquerading as a feed.

## Reproducible checks

Run `python devtools/wall_fixtures.py` for JSON and standalone HTML fixtures in
ignored `.runtime/wall-adaptive-fixtures`. Open each HTML at 1920×1080 and
1366×768. Standalone previews retain the real renderer/layout but HA's icon
icons use the same authored geometry as native HA. The seventeen fictional
scenarios cover school morning, quiet daytime, pre-pickup, leave soon, evening
finished, weekend planning, pupil-free day, weather exception, bins tonight,
doorbell takeover, active timer/media and a completely quiet day. They must
never be written to real HA states or published to the household dashboard.
Run `python devtools/e2e_wall.py` with Playwright installed for 34 browser
checks (both resolutions): no borders, empty islands, clipping or overlapping
times; preview/morning person continuity and native transition/stale recovery. This uses
only local fictional data and saves ignored review screenshots.

Tests: `tests/test_wall_composer.py`, `test_wall_cameras.py`, `test_context.py`,
`test_wall_recovery.py` and `tests/js/wall.test.mjs`. Native HA captures and actual
Pi compositor evidence remain private/ignored; screenshots are not source data.

## Appliance reliability and remaining physical checks

The existing display service reapplies 180-degree rotation and restarts Chromium.
Its launcher keeps the same profile and owned URL. Two failed HA-origin probes
show a local dark, non-sensitive connection screen; connectivity recovery returns
to the owned board. No credentials or previous plans enter the fallback page.
The rendered board also hides stale/disconnected context. Cursor is hidden on the
passive board. Existing labwc/autologin/health/voice/audio services are preserved.

The overnight presentation deliberately reduces content. **Actual monitor
brightness/wake is infrastructure, not a dark-CSS claim.** No DDC/backlight
controller is commissioned on the inspected HDMI monitor, so physical scheduled
dimming remains pending a working hardware adapter. A reboot can verify service
recovery; it is not a physical power-cut or human distance-readability test.


## School timetable input and live source evidence (0.8.32)

Calendar mappings now distinguish `timetable` (one confirmed child, ordered native
classes) from `school` (general school events). Keep the timetable selected,
verified and **Show at home** for the shared wall. Context-only, ignored, new,
excluded or unverified sources cannot enter the shared school projection.
`context_runtime` separates timetable events from household appointments before
composition; `school_timetable.select` selects the focus date and sorts periods
chronologically. Separate periods retain repeated subjects. No class bodies are
written to Home Starter settings, fixtures or logs. The existing published HA
context/recorder boundary still applies to displayed information.

School content is dated school/preparation event links first, timetable subjects
second, explicitly applicable date-scoped rules third, and **School tomorrow** /
**School today** only when none is available. No year label, kit or travel estimate
is derived from subjects. Explicit routine-exception/holiday dates suppress the
school fallback. Morning and evening share child keys; only the focus label and
real departure importance change. On smaller screens retain ordered leading
classes and an honest remaining-class count rather than shrinking all type.
Nonempty week groups show their next significant event; household events are
not repeated in generic person/context islands.

Live attribution was established from Google's existing calendar display labels
(`summaryOverride`), which HA had flattened to the same Cirrus friendly name:

| Child | Native timetable source | Original source label |
| --- | --- | --- |
| Maddie | `calendar.cirrus_calendar_3` | Maddie's Timetable |
| Edie | `calendar.cirrus_calendar_2` | Edith's Timetable |
| Flynn | `calendar.cirrus_calendar` | Flynn's Timetable |

The other two Cirrus feeds are VLC Events, not personal timetables. Their existing
context-only classification remains. Only the three identified timetable feeds
were approved for shared school display by the user's timetable request. Live
verification on 18 October read seven Monday entries per child; no subjects or
private native screenshot are committed. Calendar identity remains a native ID
mapping; no product code depends on these household-specific IDs or names.


## Reference restoration (0.8.33)

This slice changes presentation only. Calendar/timetable mappings, school date
selection, event selection, horizon and state machine are unchanged. Existing
`school.children` render in the three avatar cards. Adjacent identical subject
names collapse visually to a counted group (for example ×2); nonadjacent repeats
remain separate and scheduled-period totals are preserved. This is not a packing
rule. Week groups move to the lower-right secondary region and retain their
selected dates/events. Today appointments already in the main timeline need not
be repeated in a third right-side panel.

The clock/date and forecast share the open upper-left hero. Person cards use
subtle individual tint, large circular portraits/initials and legible facts.
The status footer uses meaningful selected native data, with camera thumbnails
only when selected. No security/camera state or household photo is invented.
The live children's person records currently have no portraits, so initials are
the correct fallback. Native photos are confined to admitted Person sources.
A before/after digest checks the live focus, school, timeline, secondary and
week data contract; real screenshots remain ignored local verification evidence.


## Invisible kiosk cursor (0.8.34)

The wall's own shadow CSS uses `cursor: none !important` for its entire surface.
While that wall is mounted at its own `/home-starter-<surface>/` route with
`?kiosk` (without `disable_km`), its component also inserts the rule into the
HA document and every open shadow root. A mutation observer covers new controls
and overlays. Navigation, kiosk escape or component removal removes the injected
styles and listeners; phone/tablet surfaces retain their own pointer behaviour.
The standalone Pi network fallback applies the same cursor rule locally.
Run `python devtools/e2e_wall_cursor.py` for pointer, reload and scope acceptance.

The actual Pi runs labwc/Wayland. `devtools/kitchen_wall/install_cursor.py` creates
a transparent cursor theme in the dedicated display account, validates its image
through the native cursor library, and covers installed cursor aliases. It sets
labwc's environment, the browser user service environment and that account's GTK
cursor preference; no X11 daemon or additional package is installed. This prevents
motion from revealing the OS cursor, including before the wall page loads.
[labwc documents its Wayland cursor-theme environment](https://labwc.github.io/labwc-config.5.html#environment_variables).
Original labwc environment and GTK preference are retained beside their settings.
To undo, restore `environment.before-home-starter-cursor`, restore the saved
`cursor-theme.before` preference, remove the owned `cursor.conf` service drop-in,
and reboot. Browser credentials/profiles and unrelated services are untouched.

Live acceptance on 18 October 2026 confirmed an actual Pi reboot and automatic
kiosk startup, then two reloads with all 533 inspected elements across 89 HA/shadow
roots resolving to `cursor: none`. Eleven native Wayland virtual-pointer motions
also produced no cursor pixels in cursor-inclusive captures with webpage cursor
hiding temporarily overridden; the probe was removed and the wall reloaded.
No physical mouse was attached. Isolated phone/tablet navigation checks restored
their original cursor styles. Private screenshots stay outside Git.

## Late-evening preview continuity (0.8.35)

The 22:00 night boundary previously set `focus.restrained` even while Tomorrow
was selected. That removed the school panel and reduced the timeline to two
items, leaving one stretched adult card. Tomorrow preview now retains its full
content through midnight; actual overnight restraint still applies afterwards.
The reference composition, CSS and Cirrus ownership/visibility choices are
unchanged. Live checks confirmed three selected Cirrus feeds with seven Monday
periods each, three person cards, all three Monday household commitments and
four upcoming-day groups, without clipping. Regression scenarios cover late
Sunday as well as weekday morning at both supported wall sizes.
