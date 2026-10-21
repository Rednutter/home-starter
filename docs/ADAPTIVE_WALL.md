# Kitchen Wall presentation

The Pi keeps its existing native HA dashboard, dedicated restricted account,
Chromium kiosk profile, systemd services, health endpoint and 180-degree output.
This is a passive shared board, not an enlarged AirTouch control surface.

When no selected camera is available, the same bottom region shows current media
title, artist and room from admitted household players. Paused/stopped players
and stale context leave no media card. Available cameras retain priority.
Playback comes from fresh MA players/active queues, deduplicated by queue ownership
rather than media title. Group members do not produce extra cards; independent
queues remain distinct. Only title/artist/room cross into the wall projection.
Radio uses its catalogue station name, never delivery URLs or transport markers.
The Lights cell keeps its large anchor icon and shows confirmed-on lights/groups
as a compact row of warm-white outline icons beneath the heading. Native icon
metadata selects the shape; unknown types use a bulb. Selected group members are
not counted twice. Off/unavailable lights have no lit icon; overflow uses +N.

The right timeline is one full-height surface. Its detailed focus-day list is
followed immediately by a subtle divider and compact future days, with no fixed
split or separate Week ahead card. Future rows yield space to today's events.
Evening/night focus-day selection and the three morning school cards are unchanged.
From noon until night mode, the school cards independently select tomorrow's
dated native classes and confirmed departure, labelled Tomorrow. This does not
move today's remaining appointments out of the main timeline or replace current
weather with a forecast. Tomorrow's school attendance is one compact household
row below today. Missing tomorrow data never reuses today's classes.

Kitchen Wall Sendspin uses the PortAudio device-name match `bcm2835 Headphones`
for its 3.5 mm stereo amp feed. An ALSA string such as
`plughw:CARD=Headphones,DEV=0` can appear accepted during startup but fail when
PortAudio opens playback. Verify a RUNNING hardware stream, not just MA's playing
state. The USB microphone/voice path is independent.
Confirmed `context.school_departures` maps child identities to local HH:MM times;
these apply only to dated native school periods, never inferred school days.
Timetables use person-tinted, subject-only lesson cards, muted completed lessons
and gentle current-period emphasis. Native times stay in the state model, not
the lesson cards; multiplier badges are hidden. Each native period owns a
grid slot; consecutive equal subjects (including Cirrus's one-minute transitions)
join into a card spanning those slots. User-confirmed Recess/Lunch gaps use slim,
unlabelled fixed-height separators. Matching bell times stay aligned across children;
different source schedules retain their own native cadence. Shared header and
footer rows keep names/departures above the aligned timetable and extra confirmed
requirements below. Night mode omits people/planning cards and retains restrained clock/weather/status.

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
timeline with a content-positioned future divider, and a readable household/status
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
controller is commissioned on the inspected HDMI monitor. Scheduled output power
now uses Wayland (see below); brightness dimming remains separate. A reboot can verify service
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

The shared chronology also includes school attendance (0.8.36). Selected native
periods supply one School row per first-period time with the attending children's
names. Classes remain in person cards. An explicit school event takes precedence
for its linked children; missing periods, suppressed dates and expired attendance
never create assumed school commitments. Other dated household events stay in
the timeline in time order. Live Monday has one 8:50 School row for three children.

## Quiet night presentation (0.8.39)

Night now runs from 20:00 inclusive to 05:00 exclusive in the household timezone.
It retains a quieter clock/date/weather header and restrained home/media status.
All person cards, timetables and household timelines are omitted from the night
DOM, with no empty planning containers. A small unboxed school departure beneath
the date appears only when all mapped children share the same confirmed future
leave time. Safety exceptions and temporary display
sessions remain available. At midnight the forecast becomes Today rather than
jumping to the following day. At 05:00 the full class presentation returns. Temperature
labels distinguish High/Low forecasts from Now observations, without arrows.
Visual night treatment does not change the Pi monitor's hardware brightness.
Boundary regressions cover 19:59, 20:00, midnight, 04:59 and 05:00. The previous
compact three-card night presentation was superseded by the quieter landscape.

Wallpapers are bundled locally with a legacy-image fallback, without remote
image requests. Morning 05:00–10:00, day 10:00–14:00, afternoon 14:00–17:00,
evening 17:00–20:00 and night 20:00–05:00 each select one landscape from their
own pool using household timezone, date and screen identity. Selection stays
fixed throughout that period and across reloads; the night selection also
survives midnight. The generated decorative scenes contain tiny hidden fictional
details; they are not live weather or household photographs. Provenance, prompts
and image hashes live in `static/wallpapers.json`. The native configuration size
test enforces HA's existing message budget.
The initial library contains 20 landscapes (four per period). Live Pi acceptance
on 19 October confirmed the normal night selection, no planning containers, the
confirmed shared school departure, local starry backdrop and restrained status.
Display/audio/voice services remained active; the screen-power schedule was not
changed. The initial twenty landscapes are unchanged. Additional generated discoveries
now use a separate 42-item local pool (forty atlas sprites plus two cutouts),
including robot animals, tiny aircraft/spacecraft and cloud/constellation shapes.
They occupy reserved visible space in the wall header and interactive Media/person
artwork, clear of copy and controls. Selection is stable per screen/daypart and
across midnight; no animation, network requests or tap targets. Generated-source
and packaged hashes are recorded in `static/decorations.json`.

Weather presentation (0.8.38) normally occupies two lines: a balanced icon and
inline temperature labels, then a short condition/preview label. Both numbers
now share the same size: Now/High by day, High/Low in preview. The group is
centred within its existing hero column. Preview omits the repeated weekday and
current observation. Only a weather exception or significant rain probability
(60% or higher) adds a third line. Missing forecast values remain explicit.

Morning recovery (0.8.39) separates durable approved-source commissioning from
ephemeral calendar data. The same source/choice signature remains mandatory;
calendar data is fetched each update and expires within 150 seconds (wall within
75 seconds). No event cache is reused on failed reads. Health reads neither
change consent nor write settings. Camera/waste verification TTLs are unchanged.
Person cards retain timetables and promote a configured Leave time, otherwise a
native first-period Starts time. Kit and travel remain explicit. Timeline times
refer to event starts; departure details are labelled separately. Missing data
does not stretch cards across the screen or claim school attendance.
Live acceptance recovered the 30-hour-old selection without re-authentication:
three cards, all 21 native periods, four household entries, repeated fresh reads
and unchanged calendar classifications. Cursor and screen-power checks passed.

## Nightly screen power

Kitchen Wall's HDMI-A-1 output sleeps from 22:00 inclusive to 06:00 exclusive in
Australia/Sydney time, independently of the wall's 20:00–05:00 content mode.
`screen_power.py` uses the existing native Wayland `wlopm` power protocol and
verifies the returned output state, including disabled HDMI after standby's
hotplug cycle. The user service/timer runs at both daily
boundaries, 15 seconds after manager startup and every minute for recovery.
Each execution reconciles the current local time, so missed timer events and
overnight reboots cannot replay the wrong power action. DST follows the local
timezone. Chromium, authentication, audio and voice remain running.

The inspected monitor briefly disconnects on standby. The merged labwc user
configuration disables automatic output re-enabling; the original rc.xml is
preserved in `rc.xml.before-home-starter-power` (empty means originally absent).
This is the [documented labwc standby workaround](https://labwc.github.io/labwc-config.5.html#entry_core_autoenableoutputs).
At wake, the service explicitly enables HDMI with `wlr-randr`, restores the
existing 180-degree rotation, then confirms power on. A disabled HDMI output
with the compositor's headless fallback is a valid off state.

Install both Python helpers in `~/.local/share/home-starter/` and the shipped
`home-starter-screen-power.service` / `.timer` in `~/.config/systemd/user/`.
Run `python3 ~/.local/share/home-starter/install_screen_power.py` once in the
dedicated account; it requires the existing `labwc -m` merged configuration.
Run `systemctl --user daemon-reload`, then
`systemctl --user enable --now home-starter-screen-power.timer` and
`systemctl --user start home-starter-screen-power.service`.
The live Pi confirmed output off → on → scheduled off while all kiosk/audio/voice
services remained active. The initial short-cycle test did not establish a full overnight wake. The later
morning failure and follow-up are recorded below.
To disable scheduling, stop/disable the timer, restore the saved rc.xml (remove
the owned rc.xml if the backup is empty), reload labwc, and enable HDMI with
`wlr-randr --output HDMI-A-1 --on --transform 180` followed by
`wlopm --on HDMI-A-1` within the graphical account's Wayland environment.


### Chronology and discovery follow-up

The detailed agenda heading and date describe the displayed day, independently
of the children's tomorrow preview. Selected future events remain eligible through
the existing 21-day discovery horizon, including subsequent weekends/weeks.
The renderer measures available height and shows a chronological prefix of whole
future rows/day headings; the divider follows the detailed entries. It refits on
resize and font readiness, without scrolling, row/day quotas or blank headings.
Distant chronology does not imply an urgent preparation requirement.

Verification: 793 Python and 72 JavaScript tests, Ruff and privacy checks passed.
All 22 fictional wall scenarios passed at 1920×1080 and 1366×768. The measured
sparse-agenda case fits eight/seven future days respectively and restores rows
after resizing. Generated interactive tablet/phone-size fixtures verify decorations
remain outside copy and controls. Live native configuration readback verified the
wall and both existing specialist panels; the Pi capture confirmed normal night
mode and equally sized forecast temperatures. Daytime fitting is synthetic browser
evidence, not a claim that daytime was observed live after the evening deployment.


### Morning HDMI recovery follow-up

On 21 October the timer remained active, but repeated morning wake requests failed.
The monitor was connected while HDMI-A-1 was disabled and NOOP-1 was powered.
labwc reported failed HDMI swapchain tests and rejected the output configuration;
Chromium/audio/voice continued. A user hard reboot restored the graphics session.
After reboot the monitor selected its preferred 1920x1080 at approximately 100 Hz.

The installed helper now requests supported 1920x1080 at 60 Hz explicitly,
retains 180-degree rotation, and makes at most three fresh state/configuration
attempts with short backoff. Individual utility calls time out after three
seconds, keeping the worst-case retry sequence inside the service timeout.
Kiosk startup pins the same mode without forcing power on outside the schedule.
A persistent graphics failure still reports failure; it is never counted as a
successful wake because a headless output is powered. No reboot, privilege rule,
audio change or compositor replacement was added.

Live verification passed a 45-second standby and a separate 120-second standby
through the installed scheduled service. Both allowed the monitor's hotplug to
settle to disabled HDMI plus NOOP, then restored physical HDMI at 60 Hz.
The installed service reported success, the power timer was re-enabled/active,
and display/audio/voice stayed active. Original helper/service files were backed
up on the Pi. The refresh-rate pin is a mitigation, not proof that 100 Hz caused
the underlying graphics failure. A full subsequent overnight interval has not
yet been observed.

### Full-width priority and dated collection follow-up

The normal weather header now leads with the selected day's forecast maximum.
Current temperature is secondary; preview uses that date's low. Daily forecast
facts generate compact storm/hail/rain/wind/heat/cold badges with explicit units.
Daily records never imply an afternoon forecast or an official severe warning.
No official-warning feed is currently configured, so that live path is unavailable.
Every schedule day uses its own dated forecast from the same model; unavailable
forecast days show a quiet dash rather than extrapolated weather.

One ranked action may occupy the entire top band, replacing weather and moving
the schedule down beside the unchanged person cards. Confirmed departures appear
15 minutes before Leave by, then retain a factual passed-time cue for ten minutes.
This does not assert attendance, departure completion or that anyone is late.
Timed preparation/start cues are lower priority. Browser expiry restores normal
weather and schedule height independently of the next context poll. Both detailed
and future rows are fitted as whole chronological entries to measured space.

Confirmed Council collections now reconcile to the separately owned native
Home Starter Bins calendar. Each actual collection date has one all-day event;
there is no preceding reminder event. Journals bind writes to the created entry
and native event UID; unknown calendars and externally edited events are preserved.
REST readback uses start/end; HA's WebSocket writes use dtstart/dtend.
The wall derives Bins out tonight after 18:00 and Bins today until noon, which is
a relevance cutoff, not evidence that collection occurred. Existing selected bin
screens are preserved, and the user-requested wall selection is explicitly saved.
Detailed rows use the supplied illustrated bins; dense rows use matching outlines.
The bottom utility slot accepts structured escaped content and defaults to the
existing household/media/camera presentation.

Live HA readback verified six unique all-day events and the Pi screenshot showed
the real tomorrow timetable, forecast and bin action. Priority layout evidence is
synthetic browser acceptance, not a claim that a departure alert occurred live.
Private screenshots and timetable payloads remain outside Git.

Priority treatment uses amber glass for soon, stronger amber for immediate action
and muted coral for a passed leave time. A departure icon and enlarged bold action
lead the header; the date and names recede. The 450 ms entrance runs once per alert
identity, never per clock refresh, and respects reduced motion.
