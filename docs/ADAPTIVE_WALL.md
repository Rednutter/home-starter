# Kitchen Wall presentation

The Pi keeps its existing native HA dashboard, dedicated restricted account,
Chromium kiosk profile, systemd services, health endpoint and 180-degree output.
This is a passive shared board, not an enlarged AirTouch control surface.

## Data and composition

`context_runtime.inspect` reads the existing verified consolidated calendar,
explicit event/person/departure links and selected household sources. It calls
`wall_composer.compose`; its `wall` output is reusable by other presentations.
No title keyword infers school, a holiday, a destination or a travel estimate.
People explain commitments; no person/location domain is permanently displayed.

The composer exposes `day_state`, `baseline_state`, `primary`, `next_movement`,
`today_items`, `future_attention`, `household_exception`, `active_context`,
`display_session`, `spans` and `valid_until`. Named states are busy morning,
quiet daytime, pre-activity, active movement, evening, overnight, weekend,
abnormal schedule and exception. Urgent context overrides the clock baseline.
Today contracts/vanishes when finished; selective future attention expands.
Upcoming rows beyond tomorrow require explicit preparation/holiday/early-attention
annotations. The horizon is at most 21 days, not a full calendar dump.

`static/wall-content.js` renders these priorities and applies only freshness,
expiry and viewport-capacity checks. `static/wall-layout.css` retains a small
clock/weather header and the approved landscape palette. No permanent child,
camera, presence, lighting or media cards. The bottom context strip appears only
for active timer/media/climate context. Safety exceptions outrank sessions.

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
elements require native HA for their final appearance. The twelve fictional
scenarios cover school morning, quiet daytime, pre-pickup, leave soon, evening
finished, weekend planning, pupil-free day, weather exception, bins tonight,
doorbell takeover, active timer/media and a completely quiet day. They must
never be written to real HA states or published to the household dashboard.

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
