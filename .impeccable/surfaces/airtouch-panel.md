---
version: 1
slug: airtouch-panel
primary_target: home_starter/server/homestarter/panel.py
related_targets: [home_starter/server/homestarter/static/panel-layout.css, home_starter/server/homestarter/static/panel-content.js, home_starter/server/homestarter/static/panel-climate.css, home_starter/server/homestarter/static/panel-details.css]
---

# AirTouch household panel

MODE: Operate. User-pinned AirTouch reference; code-led adaptation to truthful HA data.

## Direction contract

THESIS: One landscape household surface; climate leads without a scrolling thermostat stack.
OWN-WORLD: Dark neutral overview canvas, white Roboto, rounded contextual photographic panels and subdued slate inactive edges. Blue signals operating Climate or selected household navigation. Existing navy/cyan Climate/detail styling remains unchanged.
STORY: Read live climate and household context, then open preserved native controls. Missing capabilities remain explicit.
FIRST VIEWPORT: Clock/date/weather header; climate occupies the left two rows, Today above Call/Cameras on the right, Media/Home below; House plus saved people span the bottom as primary navigation; Ambient and kiosk Settings are secondary accessible Display shortcuts. Narrow containers wrap household items whole and put utilities on a separate row without clipped controls.
FORM: User-pinned composition, no seed tournament. Mature button-card supplies layout; native HA supplies control subviews and permissions. Only reviewed specialist publication changes.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

CLIMATE CONTINUITY: The Climate route retains its existing scoped navy/cyan palette and photographic main-system panel; native thermostat and zone actions remain unchanged. Main system beside rooms; each uniquely device-linked zone includes its own readonly airflow. Thermometer readings, full-width +/- setpoints, compact native mode icons and damper bars have distinct hierarchy. Keep ordinary display states visual, with explanatory wording in accessible labels/tooltips. Stack system above rooms at 1100px and below; rooms become a single column at 720px. Preserve native Back and all other subviews.

ROOM MATERIAL: Reuse the generic backdrop under quiet navy overlays. Place name/reported temperature beside native controls to reduce dead space; retain the full-width damper bar. Finish verdict: ship after landscape, narrow and tall-tablet review.

VIEWPORT FILL: Main Climate row and nested room cards stretch through available height; inactive notices remain collapsed. Existing saved ordering supplies household column groups. Native responsive acceptance and finish review: ship.

DETAIL CONTINUITY: Within the specialist landscape panel, Rooms and individual rooms, Music, Today, household context, saved people and kiosk Settings inherit the navy/cyan palette and existing generic backdrop. Preserve admitted native nested cards, source configurations, section visibility, native Back and people admission boundaries. Auto-fit columns have a (280px) minimum and shrink to the available width on narrow screens. Ambient/dark and the primary Climate presentation remain unchanged. Missing overview destinations show truthful empty states; Call and Cameras open static setup-status pages without calling services, capabilities or camera feeds. Selected bins retain their existing condition and expiry.

DETAIL IMPLEMENTATION: One shared button-card template carries detail styling/backdrop so the generated dashboard stays within HA's (4MiB) WebSocket limit; an eight-person regression checks the limit and three embedded images. Native card configurations keep `do_not_eval` boundaries. Semantic h1/h2 headings preserve escaped titles, room-stack navigation icons use compact (40px) sizing, and native card radii/palette plus the scoped dark media fill retain continuity. Only headings allow arbitrary word breaks, preserving narrow weather units.

DETAIL ACCEPTANCE: Docker recovered after stale runtime-only socket directories were preserved and recreated together; containers, images and settings remain intact. Disposable HA (2026.10.0) with button-card (7.0.1) supplies fresh native browser evidence. The passing final stabilized native run produced 48 fresh full-page captures across eight empty/populated detail pages at 1280×720, 800×1280 and 390×844, plus 12 saved-person viewport captures across baseline/populated states. Capture helpers wait for fonts and stable geometry and reload each viewport. Native navigation/Back/reload, kiosk viewer/admin scope, light toggle/restore, climate target restore, calendar/player rendering and Play control visibility, offline/idle and bin expiry passed in the final stabilized run; the final visual review returned ship at native Home Assistant fixture/browser scope, with no remaining blocking findings. The upstream native media-card startup `_stateObj`/`_computeProgress` exception is reproduced on an unmodified native sections view and logged separately in ignored browser-error evidence; other errors fail acceptance. This does not prove audible playback, physical-screen operation or live household publication. No new assets or provenance changes.


## Overview refinement contract

Preserve the asymmetric six-card board and existing clock/date/selected-weather information. Climate and Home reuse the generic room image. Today shows a decorative meal, Call an intercom, Cameras a porch and Media a speaker. Text-side directional neutral gradients reveal the photographs to the right while protecting contrast. Four new JPEGs carry exact prompts and origin metadata; `static/panel-imagery.json` records source/output hashes. None depicts the household, verifies a capability or supplies a live feed. Do not invent sources, members, portraits or commissioning status.

Climate is blue only for reported operation while its state is not Off; Off takes priority over stale activity. Idle and Off stay neutral. “N of M zones enabled” describes admitted zone state separately from HVAC operation; unavailable zones are explicit. Uncommissioned/unselected capability explanations remain truthful secondary copy, below titles and live readings. The existing 30s refresh remains.

Household links are 76–118px wide with 70px base / 66px compact target heights. Navigation is 84px base / 76px compact. Ambient and Settings are separate 52px square shortcuts with accessible names. At container widths through 720px, household links wrap and utilities occupy a separate row. No reference-image family names or avatars ship. Settings remains the kiosk escape; Ambient remains manual.

### Reference disposition matrix

| Reference property | Disposition | Implemented evidence |
| --- | --- | --- |
| Asymmetric six-card landscape geometry | Match | Climate spans two left rows; Today above Call/Cameras; Media/Home below. |
| Dark neutral ground and inactive edges | Match | Overview-scoped charcoal canvas and slate borders; native Climate/detail navy tokens remain intact. |
| Blue emphasis | Match | Operating Climate and selected household item; idle/Off neutral, keyboard focus explicit. |
| Contextual photographs | Justified adaptation | Four generated decorative photographs plus reused room image; embedded provenance replaces any real-household/capability implication. |
| Directional overlays and readable white Roboto | Match | Dark text-side gradient and pinned Roboto preserve the supplied visual direction. |
| Capability/setup information | Justified adaptation | Honest secondary setup copy replaces unsupported reference capabilities and source claims. |
| Household destinations | Justified adaptation | House and saved people only, configured order, no fictional family members or portraits. |
| Ambient/Settings hierarchy | Match | Separate secondary Display icons with 52px touch targets; narrow layouts use a separate row. |
| Climate state/zone information | Justified adaptation | Off overrides stale activity; enabled-zone counts do not claim HVAC operation. |
| Small-screen composition | Justified adaptation | Whole-item wrapping and vertical reflow preserve controls instead of shrinking/clipping the landscape board. |
| Native Climate and details | Preserved scope | Existing navy/cyan controls, backdrop, contents, Back and admission boundaries remain unchanged. |

### Refinement evidence and limits

Latest native evidence: `screens/panel-ui/{panel-landscape,compact-landscape,narrow,cooling,idle,off-zones-enabled}.png`. Full `devtools/accept_panel_native.py --kiosk` passed native controls with restore, navigation, reload, kiosk escape/re-entry and active/Off transitions. (538) Python and (30) JavaScript tests passed; the eight-person payload is (1,659,321 bytes), under (4MiB). The once-run detector has no errors; pinned Roboto and advisory overview-token findings are intentional scoped choices. The finish review's documentation-sync disposition is resolved by this contract and DESIGN.md.

Home Starter (0.8.12) is prepared locally; live (0.8.11) remains unchanged. Physical-tablet acceptance and actual hardware operation remain unverified. Automatic idle → Ambient → Dark and wake-return policy are not implemented, and default-dashboard/app startup is not configured. Browser captures and tests do not establish those outcomes.
