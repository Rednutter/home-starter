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
OWN-WORLD: Reference navy canvas, white Roboto, cyan climate accent, rounded photographic panels, fine cool borders.
STORY: Read live climate and household context, then open preserved native controls. Missing capabilities remain explicit.
FIRST VIEWPORT: Clock/date/weather header; climate occupies the left two rows, Today above Call/Cameras on the right, Media/Home below; household navigation spans the bottom. Narrow containers reflow without clipped controls.
FORM: User-pinned composition, no seed tournament. Mature button-card supplies layout; native HA supplies control subviews and permissions. Only reviewed specialist publication changes.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

CLIMATE CONTINUITY: The Climate route uses the same scoped navy/cyan palette and photographic main-system panel; native thermostat and zone actions remain unchanged. Main system beside rooms; each uniquely device-linked zone includes its own readonly airflow. Thermometer readings, full-width +/- setpoints, compact native mode icons and damper bars have distinct hierarchy. Keep ordinary display states visual, with explanatory wording in accessible labels/tooltips. Stack system above rooms at 1100px and below; rooms become a single column at 720px. Preserve native Back and all other subviews.

ROOM MATERIAL: Reuse the generic backdrop under quiet navy overlays. Place name/reported temperature beside native controls to reduce dead space; retain the full-width damper bar. Finish verdict: ship after landscape, narrow and tall-tablet review.

VIEWPORT FILL: Main Climate row and nested room cards stretch through available height; inactive notices remain collapsed. Existing saved ordering supplies household column groups. Native responsive acceptance and finish review: ship.

DETAIL CONTINUITY: Within the specialist landscape panel, Rooms and individual rooms, Music, Today, household context, saved people and kiosk Settings inherit the navy/cyan palette and existing generic backdrop. Preserve admitted native nested cards, source configurations, section visibility, native Back and people admission boundaries. Auto-fit columns have a (280px) minimum and shrink to the available width on narrow screens. Ambient/dark and the primary Climate presentation remain unchanged. Missing overview destinations show truthful empty states; Call and Cameras open static setup-status pages without calling services, capabilities or camera feeds. Selected bins retain their existing condition and expiry.

DETAIL IMPLEMENTATION: One shared button-card template carries detail styling/backdrop so the generated dashboard stays within HA's (4MiB) WebSocket limit; an eight-person regression checks the limit and three embedded images. Native card configurations keep `do_not_eval` boundaries. Semantic h1/h2 headings preserve escaped titles, room-stack navigation icons use compact (40px) sizing, and native card radii/palette plus the scoped dark media fill retain continuity. Only headings allow arbitrary word breaks, preserving narrow weather units.

DETAIL ACCEPTANCE: Docker recovered after stale runtime-only socket directories were preserved and recreated together; containers, images and settings remain intact. Disposable HA (2026.10.0) with button-card (7.0.1) supplies fresh native browser evidence. The passing final stabilized native run produced 48 fresh full-page captures across eight empty/populated detail pages at 1280×720, 800×1280 and 390×844, plus 12 saved-person viewport captures across baseline/populated states. Capture helpers wait for fonts and stable geometry and reload each viewport. Native navigation/Back/reload, kiosk viewer/admin scope, light toggle/restore, climate target restore, calendar/player rendering and Play control visibility, offline/idle and bin expiry passed in the final stabilized run; the final visual review returned ship at native Home Assistant fixture/browser scope, with no remaining blocking findings. The upstream native media-card startup `_stateObj`/`_computeProgress` exception is reproduced on an unmodified native sections view and logged separately in ignored browser-error evidence; other errors fail acceptance. This does not prove audible playback, physical-screen operation or live household publication. No new assets or provenance changes.
