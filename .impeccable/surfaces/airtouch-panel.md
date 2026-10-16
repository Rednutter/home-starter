---
version: 2
slug: airtouch-panel
primary_target: home_starter/server/homestarter/panel_pages.py
related_targets: [home_starter/server/homestarter/panel.py, home_starter/server/homestarter/static/panel-layout.css, home_starter/server/homestarter/static/panel-pages.css, home_starter/server/homestarter/static/panel-shell.js, home_starter/server/homestarter/static/panel-pages.js, home_starter/server/homestarter/static/panel-climate.css]
---

# AirTouch household page system

MODE: Operate. The user-approved House (0.8.12) is the visual foundation, extended by code-led focused pages; House is not redesigned.

## Direction contract

THESIS: House plus actual configured people, each with their own context and listening identity; rooms and players remain physical shared destinations.
OWN-WORLD: Approved neutral near-black/charcoal, white Roboto, subdued slate edges, restrained active/selected blue, contextual photographs and directional text-side overlays across every owned route. No separate navy application world.
STORY: Glance → focused feature → control → Back/House. Personal feature Back returns to that person; room Back returns to its owning Rooms view. Direct loads and reloads preserve explicit destinations.
FIRST VIEWPORT: Shared status header, clear Back/title, purposeful body and persistent household footer, including Dark's Wake/safety state. Person landing uses compact rooms, listening availability and scoped Today; richer controls belong on focused routes.
FORM: One shared button-card page template and registry reuse approved House tokens/material. Purpose-built Today, Call, Cameras / Door, Media, Rooms and person routes; native Climate thermostat, zones, setpoints and readonly damper semantics remain intact. No generic entity/media/calendar pages or fabricated integrations.
FINISH: Final native acceptance is passing; the reviewer scored the listed visual fixes resolved at disposable HA fixture/browser scope. Record only observed fixture/browser outcomes, retain raster provenance, and keep live commissioning/physical-device limits explicit.

## Shared material and geometry

House retains its asymmetric six-card board and time/date/weather. Climate spans the two left rows; Today above Call/Cameras, Media/Home below, House and saved people in the footer. Ambient and kiosk Settings are secondary Display utilities. Existing saved order supplies people; no sample family, portrait or capability ships.

Focused pages use the same neutral canvas, Roboto, slate edges and image treatment. Feature corners/padding are (24px), control groups have (20px) corners, actions (14px), Back/House links (16px). Headings use (26/24/22px), body (20px), supporting copy (18px), quiet copy (16px). Buttons/selects have (56px) minimum dimensions. Icons have bounded hosts and zero inherited margin. Keyboard focus remains explicit. Native Climate retains its own controls within the neutral wrapper; blue is meaningful state/focus, never the default page ground.

Contextual Today, Call, Cameras and Media photographs reuse their existing assets; Climate/Rooms use the room material. Directional overlays protect content and reveal imagery on the opposite side. Five existing rasters retain prompt/origin metadata and source/output hashes in `static/panel-imagery.json`. They are decorative invented settings, not household evidence, working hardware or live feeds. No new assets; provenance scan: five rasters, zero missing records.

The House board preserves its (720px) narrow-container and (750px) compact-landscape reflow. Focused feature grids auto-fit from a shrinking (280px) minimum. Person/Media columns stack through (800px), headings and briefing rows wrap through (720px), and Climate stacks system above rooms through (1100px). Feature content scrolls within the viewport between header and persistent footer; the household menu stays visible before and after scrolling, including narrow House boards and Dark. Household targets remain (76–118px) wide, (70px) base / (66px) compact high, within an (84px) / (76px) tray. Secondary Display targets remain (52px). Narrow footer links wrap whole and utilities receive their own row.

## Content and identity

Today consumes the existing context engine: one actionable lead and up to six later rows, with chronology beneath its headline and honest source expiry. Personal Today needs an explicit selected native Person source uniquely linked to the confirmed member; absent linkage yields an empty personal briefing, never a House clone. Projection scope includes surface, epoch and person. People tabs select shared-wall context, not authentication or confidentiality from other display users or HA state readers.

Call shows commissioned destinations or simplifies to incoming/active controls. Cameras shows one selected source with only explicit supported Talk/Open actions; entry actions require association, current event and actual-user permission. Media separates listener identity/progress from speaker destinations, feature-gates transport/grouping/volume and labels native volume as the speaker's scale. Destination selection alone never starts playback or advances a book. Children default to explicitly assigned room speakers and may choose expressly permitted alternatives. Provider services own durable scheduling/progress.

Rooms represent actual admitted physical areas with useful supported light, fan, climate and normal-blind controls. Security/entry devices remain status-only here. Climate distinguishes operation from selected mode and enabled zones; Off overrides stale activity. Zone/damper pairing requires unique registry-device evidence. Missing temperature is omitted; unavailable damper position is explicit and the percentage describes opening, not measured airflow.

Home Starter owns commissioning. Current readiness does not produce new call, camera-entry or personal-listening bindings: ordinary generated pages therefore show setup states. Internal opt-in revisioned owned projections and explicit registered service descriptors are future commissioner contracts, not a parallel setup UI or live integration proof. Raw discovery, a source name or person tab cannot establish readiness. No credentials are stored in page metadata.

## Architecture and kiosk

`panel_pages.py` builds routes, one shared `home_starter_page` template and a compact per-House/per-person source registry. `panel-shell.js` supplies status/header/safety/navigation; `panel-pages.js` supplies feature bodies; `panel-pages.css` extends approved House CSS. Route/shared metadata are JSON strings parsed inside the renderer, keeping household labels inert to button-card recursive evaluation. Text is escaped, raw provider attributes are not duplicated, and native Climate configuration retains `do_not_eval`. Shared images and registry stay below HA's (4MiB) message limit for an eight-person dashboard.

Explicit specialist `surface.kiosk` requires installed Kiosk Mode and the validated uniquely named dedicated nonadministrator viewer. All owned routes hide HA header/sidebar consistently, including Settings, Ambient and Dark. Settings preserves Profile/app settings, Panel mode and Exit panel to HA Overview with `disable_km`; HA (2026.10) redirects its legacy Overview route to `/home/overview`. Administrators, other accounts and dashboards retain native chrome. Supported HA navigation remains inside the Companion app. This changes presentation, not permissions, account appearance or a startup URL.

Ambient/Dark are manual states with Active/Wake return and safety attention. Automatic inactivity, incoming-event takeover from another route, wake/return coordination, device power and app startup/default-dashboard remain separate work. Incoming call/door UI exists inside focused pages, without a claimed background coordinator.

## Verification and release boundary

Started from `main` (0.8.12), commit `13be2ad4b80d653ea7d5fbaecda6cd1d8e99d9b0`; (0.8.13) is local page-system work. No Green deployment/publication is part of this task.

Final disposable HA acceptance (`.runtime/panel-pages-native/result.json`) passed on HA (2026.10.0), button-card (7.0.1) and Kiosk Mode (15.0.0). `screens/panel-pages-ui/` contains 44 final captures across 13 representative routes at (1280×720), (800×1280) and (390×844), plus House, Dark and three populated Today/person captures. Browser errors are empty; actual fixture light and native thermostat actions were restored; six-zone layout and Settings escape passed. Fictional zones use distinct actual fixture areas, avoiding misleading room inventories. All (547) Python and (42) JavaScript tests pass; ruff check/format pass.

The first finish review's five issues were addressed: icon geometry, person hierarchy, personal identity, kiosk ground/escape and Today heading hierarchy. Final icon margins were explicitly reset and fictional room assignments corrected before final captures. The reviewer scored the listed visual fixes resolved at disposable HA fixture/browser scope; earlier native-detail ship records are historical evidence only. The detector ran once: ten advisory type/color findings plus the pinned-Roboto warning, no errors. Scoped token documentation reconciles the intentional roles without changing approved House values.

Browser fixture evidence does not establish live commissioning, audible playback, actual call/camera services, household loudness calibration, physical AirTouch operation or automatic lifecycle behavior. Technical source of truth and adapter/privacy limits: `home_starter/{AIRTOUCH_PANEL.md,HOUSEHOLD_CONTEXT.md,MUSIC.md}`.
