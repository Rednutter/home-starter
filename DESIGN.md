---
name: Home Starter
description: Existing administrator styling, native household dashboards and a scoped AirTouch specialist panel.
colors:
  bg: "#f4f5f7"
  card: "#ffffff"
  text: "#1c1f24"
  muted: "#5f6672"
  line: "#e2e5ea"
  accent: "#0b6fb8"
  accent-ink: "#ffffff"
  ok: "#1f7a4d"
  warn: "#9a5b00"
  bad: "#b3261e"
  info: "#0b6fb8"
  tile: "#f7f8fa"
  dark-bg: "#111317"
  dark-card: "#1a1d22"
  dark-text: "#e8eaed"
  dark-muted: "#a0a7b2"
  dark-line: "#2b3038"
  dark-accent: "#4aa3e6"
  dark-accent-ink: "#0b1620"
  dark-ok: "#5fcf96"
  dark-warn: "#f0b45a"
  dark-bad: "#ff8a80"
  dark-info: "#7dbdf0"
  dark-tile: "#20242a"
  panel-canvas: "#09131b"
  panel-text: "#f7f8fa"
  panel-muted: "#cad3db"
  panel-border: "#52606b"
  panel-climate-accent: "#56baff"
  panel-nav: "#081017"
  panel-nav-active: "#103e59"
  panel-nav-active-text: "#70c7ff"
  panel-focus: "#82d2ff"
typography:
  body:
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    lineHeight: 1.45
  headline:
    fontSize: "1.45rem"
    letterSpacing: "-0.01em"
  section:
    fontSize: "1.05rem"
  title:
    fontSize: "1.15rem"
  small:
    fontSize: "0.875rem"
  tile-label:
    fontSize: "0.78rem"
    letterSpacing: "0.04em"
  preview-clock:
    fontSize: "clamp(2rem, 7vw, 4rem)"
  panel-body:
    fontFamily: "Roboto, Arial, sans-serif"
    fontSize: "20px"
    lineHeight: 1.4
  panel-title:
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.2
  panel-temperature:
    fontSize: "clamp(58px, 7.5cqw, 82px)"
    fontWeight: 600
    lineHeight: 1.05
rounded:
  input: "8px"
  button: "10px"
  confirmation: "12px"
  card: "14px"
  badge: "999px"
  panel-tile: "24px"
  panel-tile-narrow: "20px"
  panel-nav: "22px"
  panel-nav-item: "16px"
spacing:
  action-gap: "8px"
  field-gap: "12px"
  section-gap: "16px"
  card-padding: "18px"
  panel-gap: "14px"
  panel-tile-padding: "22px 24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.button}"
    padding: "9px 14px"
  button-default:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "9px 14px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
    padding: "9px 14px"
  input:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.input}"
    padding: "10px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "{spacing.card-padding}"
  panel-tile:
    textColor: "{colors.panel-text}"
    rounded: "{rounded.panel-tile}"
    padding: "{spacing.panel-tile-padding}"
  panel-nav-active:
    backgroundColor: "{colors.panel-nav-active}"
    textColor: "{colors.panel-nav-active-text}"
    rounded: "{rounded.panel-nav-item}"
---

# Design System: Home Starter

## Overview

**Creative North Star: "Code-led Operate"**

Preserve the incumbent Home Assistant-like administration interface: compact system typography, blue actions, neutral bordered cards and progressive disclosure. The household screen setup extends this identity rather than introducing another visual world.

Home Starter owns the administrator setup and its non-operating layout preview. Generated household dashboards use native Home Assistant cards and the viewer's theme. Their chrome, typography, card styling and sidebar are Home Assistant's responsibility; do not treat those screenshot values as Home Starter tokens. V0.3 establishes admission, hierarchy and generation boundaries, not a finished visual design for every household profile. Operational limits live in [SURFACES.md](home_starter/SURFACES.md).

**Scoped specialist world: AirTouch household panel.** The explicitly requested reference-led AirTouch overview introduces a distinct navy, photographic, white-Roboto and cyan-accented panel. Its direction comes from the supplied `home_starter_airtouch_reference.png` and the contract in `.impeccable/surfaces/airtouch-panel.md`. The `panel-*` tokens apply only to this specialist overview. Administration retains Code-led Operate; native control subviews and Home Assistant chrome retain native styling. The panel reads household state and opens those preserved controls.

**Key Characteristics:**
- Compact administration with collapsible details.
- Explicit settings, preview and publication states.
- Native household controls with room-based compression.
- Quiet exceptions and a dedicated air-conditioning hierarchy.

## Colors

The admin palette uses blue for actions and focus, neutral surfaces for structure, and semantic color for status. Frontmatter records the light palette and the exact dark overrides from `styles.css`; `prefers-color-scheme: dark` switches them together.

### Primary
- Accent blue: links, primary buttons, selected outlines, text selection and focus rings.
- Accent ink: text on accent-filled controls, including the dark scheme's darker ink.

### Secondary
- Ready green, warning amber and error red: established status semantics. Informational blue supports notices and progress; color accompanies text rather than replacing it.

### Neutral
- Page background, card white and tile tint separate surfaces.
- Main ink and muted text distinguish labels from explanation.
- Pale divider lines provide card boundaries and row separation.

### AirTouch specialist scope

Panel canvas and navigation use deep navy; panel text and muted text separate primary readings from supporting context. The cool border defines tile edges. Climate accent identifies the climate icon; selected navigation combines its filled blue surface, lighter text and `aria-current`. Panel focus supplies a visible inset outline. These reference palette choices are intentional and do not redefine administrator semantic colors.

## Typography

Use the existing system font stack throughout administration. Heading levels remain modest: page heading, section heading and title use the corresponding frontmatter roles; small text explains status, suitability and preview limits. Tile labels are uppercase with tracked letters. Preview clocks use responsive sizing and tabular numerals. Native dashboard typography remains theme-owned.

The AirTouch overview intentionally uses native Roboto with Arial/sans-serif fallbacks. Large tabular temperature numerals lead the panel; tile titles, body readings and smaller detail text follow. Clock and date remain compact rather than competing with climate. The panel roles above describe the landscape base; compact landscape reduces titles to (22px), body to (18px) and temperature to (62px). Native thermostats keep their native type.

## Layout

Admin content is centered in a (920px) maximum-width wrapper with (20px 16px 48px) padding. Cards use the documented padding and (16px) bottom separation. Actions wrap; screen fields use an auto-fit grid with (200px) minimum columns. Preference rows keep item identity and Pin/Hide together, with explicit move buttons below; their list scrolls above (420px) height.

At (560px) and below, cards use (14px) padding, screen fields and preview sections become one column, and action buttons flex to the available width. Existing overview tiles become two columns, then one at (340px). Phone, specialist and bedside layout previews cap at (440px) and use one column.

Generated native dashboards use Sections. Phone, bedside and specialist Home views allow one column; other profiles allow up to three. Touch primary navigation is House plus saved people in configured order. Climate, Today, Home / Rooms and Music expand into contextual subviews with explicit back paths; missing sources are omitted. Specialist gives climate a dominant thermostat, while tablet and phone use compact glances. Rooms group only admitted entities into a native navigation Button plus templated Markdown summary, then open a room subview. They do not rely on automatic Area-card summaries. Conditional exception content and its section headings disappear in normal states. Manual Ambient and Dark are contextual display states; Dark preserves a visible Wake target and HA chrome. Both retain safety interruptions.

### AirTouch overview layout

The selected specialist overview replaces the scrolling thermostat stack with one landscape board: clock/date/weather above, dominant climate across two left rows, Today above Call and Cameras on the right, Media and Home beneath, then full-width household navigation. The three columns use (2fr 1fr 1fr), with the bottom row weighted at (.7fr). The viewport frame reserves native HA's (56px) header. Safety attention appears before the board when present. The exact first-viewport composition is scoped to this panel, not a template for other profiles.

At a container width of (720px) or less, the panel grows vertically: climate and Today span both columns, Call/Cameras share a row, Media and Home follow, and navigation wraps. At viewport heights of (650px) or less with widths above (720px), smaller spacing/type and a (112px) bottom board row preserve compact landscape density. Household links keep (56px) minimum width; navigation targets are (56px) tall at base and (52px) in compact landscape. Personal pages retain their existing admission boundary and native contents with back paths.

## Elevation & Depth

Admin cards and rows use borders and tonal layering. There is no ambient card shadow. The selected outcome uses an inset accent stroke; confirmation panels use accent borders. Preserve visible focus outlines: (3px) accent with (2px) offset for buttons and (3px) for fields, links and summaries.

Progress width transitions over (0.4s ease); indeterminate progress uses (1.4s ease-in-out). Reduced motion stops that animation. Native dashboard elevation and motion remain theme-owned.

The AirTouch overview uses dark gradient overlays on a generic room backdrop, cool fine borders and tonal separation without card shadows. Climate has a cooler overlay; Today/Home have warmer neutral overlays. Call and Cameras use solid surfaces. The shipping `static/panel-room.jpg` is generated imagery with embedded provenance; it contains no user photograph. Keep text contrast in the overlay rather than relying on details of the image. The panel introduces no decorative animation.

## Shapes

Use the existing gently rounded cards, smaller rounded inputs and buttons, and pill badges. Row dividers carry dense lists; do not wrap every preference or preview item in another card.

The AirTouch overview deliberately uses larger rounded photographic tiles, a rounded navigation tray and inset rounded selected items, using the scoped panel radius tokens. Its fine (1px) tile borders carry structure. These reference-derived radii are intentional and remain local to the specialist panel.

## Components

### AirTouch household panel

An installed same-origin HACS button-card module renders the custom overview; it does not replace native HA thermostats or permissions. The outer card has no action. Real links inside the panel open retained climate, Today/context, room and media subviews where those targets exist; their keyboard focus uses a (3px) inset panel outline. Household navigation contains House, configured people and Ambient; the active page is explicit. The known offline climate remains inspectable through native controls without inventing a temperature.

Climate distinguishes reported activity from selected mode: `hvac_action` supplies Idle/Cooling/Heating when available; fallback text says Cool mode or Heat mode rather than asserting activity. Missing climate reports Connection unavailable and a temperature dash. Today prioritizes relevant bin context and reports stale schedules textually. Calendar commitments, media and light summaries use selected household sources. Call and Cameras remain visibly uncommissioned/unselected with no fabricated action or imagery. No capability label establishes commissioning or working hardware.

Evidence: `home_starter/server/homestarter/panel.py` and `static/{panel-layout.css,panel-content.js,panel-room.jpg}`. Eight local captures in `screens/panel-ui/` cover `landscape.png`, `compact-landscape.png`, `narrow.png`, `native-climate-controls.png`, `offline.png`, `bins-tonight.png`, `stale.png` and `idle.png`. The regenerated captures include admitted, visible fixture weather; native acceptance verifies header bounds below (70px) at all tested sizes. The weather icon has explicit (26px) width, height and flex basis with no margin, preventing inherited button-card sizing from enlarging the header. The fresh finish review found composition, navigation, typography and density at the achieved ceiling. Its material activity-label finding was fixed and tested. The detector ran exactly once; native Roboto and the reference palette/radii remain intentional advisories.

Disposable Home Assistant (2026.10.0) with button-card (7.0.1) passed nonadministrator navigation, a native thermostat target increase and restore, and reload. This proves the tested native integration flow only. On the actual household Green, all climate entities were unavailable before the change; neither these captures nor disposable tests validate actual AirTouch hardware operation. Physical-screen acceptance and real climate operation remain separate. Captures are local evidence, not product assets or household photography.

Admin buttons have primary, default and transparent ghost variants. Hover changes the border; disabled controls use (0.55) opacity. Fields retain visible labels, native select behavior and full-width screen inputs. Navigation uses wrapping underlined links; collapsible details keep advanced settings discoverable without crowding the main flow.

First-run commissioning occupies the existing administration card separately from maintenance. While saved setup loads, show a truthful reading status and keep maintenance content hidden. Active setup follows Welcome, Prepare, Found, Household, Choose, Configure, Review and Verify in a wrapping ordered list; identify the current step with text weight, an underline and `aria-current="step"`. Retain the existing palette and type ramp. Returning commissioned homes open maintenance; older installations offer optional Finish setup alongside house status without implying their configuration is missing.

Commissioning uses native checkboxes, selects, labeled fields and disclosures for people, source details and selected capability questions. Summaries have a minimum (44px) touch height and wrap long names; fieldsets shrink within narrow screens. Before the single Set up my home action, consolidate household choices, selected and skipped capabilities, sources, displays, automatic changes, sign-in needs, manual work and generated-view details. Busy actions disable inputs and report scanning or saving. Results keep saved configuration, publication, supported verification, incomplete checks and deliberate skips visibly distinct; retain fix, retry and explicit display-confirmation actions where applicable. A loading failure offers Reload saved setup rather than presenting a fresh home.

Returning visits lead with House status and New / changed things in the existing bordered cards. Keep all nine navigation links available: House status, Home Readiness, New / changed things, Screens, People, Music, Climate, Activities and Review setup. Links wrap on narrow screens and open any containing disclosure before reaching their destination. Review setup starts collapsed for saved installations; commissioning owns new-home preparation. An unreadable state presents a recovery message rather than restarting onboarding.

Home Readiness uses the same bordered card and native disclosures. Summaries pair capability titles with text status, offer a minimum (44px) touch height and wrap long names. Build fields only when their disclosure opens; preserve open items during form updates. Group related choices with labeled fieldsets that can shrink within narrow screens. Show detailed source, display and service questions after explicit Wanted intent; retain Not now and Not wanted as saved decisions.

Keep readiness plans visibly separate from working configuration. Status text reports unsaved choices and incomplete inventory; unsaved choices block refresh and verification. Calendar and waste source verification follows saving, while unsupported end-to-end checks remain explicitly incomplete with a service handoff. Keep credentials in Home Assistant or Music Assistant. Discovery, installation and saved choices must not appear as proof of operation.

Reset Home Starter setup is a nested disclosure inside Review setup. Explain its local scope and retained recovery/protection data before the confirmation field; enable reset only after the exact text `RESET HOME STARTER`. Keep the destructive action visually subordinate to routine checks and screen access.

Household setup identifies screen type, room and person before generation. Preferences explicitly distinguish person choices that follow a person from physical-screen choices that stay with a display. Pin, Hide and move controls never bypass suitability or account permissions; safety Hide is disabled.

Save settings precedes Generate screen; unsaved changes invalidate the preview. The preview explains that controls become live in Home Assistant and that templates/calendar contents must be checked there. Review publication requires an explicit add/update action. Successful save/readback exposes Open dashboard and asks for control verification on the intended screen. Do not present preview readiness as verified publication.

Native Sections, Tile, Markdown, Clock, Thermostat and Calendar form the household screen vocabulary, with native Media control and Weather where supported. Specialist screens put alerts before dominant air-conditioning thermostats. Wall dashboards use a large clock and informational context, exceptions and activity, with no generated control widgets, actionable taps or room navigation. This constraint applies to generated dashboard content; native Home Assistant chrome remains present.

### Physical screen commissioning

Physical screen commissioning extends the existing Screens disclosure with the same system typography, neutral borders, native selectors and subordinate ghost actions. Lead with the distinction between dashboard publication and physical commissioning, then the fixed/shared screen selector and its current state, issue and separately dated authentication, restart and owner-confirmed physical evidence. Keep account preparation and physical verification in two bounded disclosures. Checkbox labels retain (44px) minimum touch heights, fieldsets shrink on narrow screens and the check-page address wraps without overflow. Busy actions disable controls; reading, waiting, failure and saved/readback messages remain explicit.

Account creation, passwords, reauthentication and recovery hand off to native HA. Explain the selected account's permissions and local-only preparation before explicit confirmation; a dashboard does not restrict a normal user's access. Confirming the same valid account preserves its checks. A different account or changed account/dashboard settings requires fresh session, restart and physical checks. Passive read-only walls retain an unresolved verification state because the current native check cannot be pressed by that account.

The isolated native helper/check dashboard proves which account pressed it; it does not identify the hardware or change the intended dashboard. Show the waiting stage and (15-minute) attempt expiry. Separately request the owner's physical-screen report of intended dashboard, default landing, working controls and actual restart method. Authentication and a post-restart press must remain distinct from that report; neither publication nor a press on another device is physical-screen proof. Explain that signing out or clearing browser data removes persistence and that future session revocation is not monitored.

Evidence: `home_starter/server/homestarter/static/{screen-identity.js,index.html,styles.css}` and the scoped surface contract in `.impeccable/surfaces/screen-identity.md`. The scoped finish review returned ship; physical household acceptance remains separate from implementation and review evidence.

### Music addition evidence

Music extends Code-led Operate in maintenance and commissioning: the same blue actions, flat bordered card, modest headings and system font stack (Segoe UI verified on the captured Windows browser). The reading column caps at (72ch), wraps long content and keeps full-width native selectors. Native connection and source-repair disclosures use (44px) minimum summaries. Installation/HA health remains a separate disclosure below source and speaker checks.

The API connection uses a labeled password field; provider sign-in stays in Music Assistant. Read-only inspection lists actual providers; native selectors scope the check, and playback instructions hand off to Music Assistant. Text distinguishes loading, errors, busy actions and attributed active playback awaiting mandatory hearing confirmation. Verification requires matching player, source, queue and item with fresh device status, then the administrator's audible confirmation; its scope is one source and speaker with (24-hour) expiry. Advancing device progress is separate, optional evidence and remains explicitly unverified for infrequently reporting speakers. Installation and provider labels are never playback proof.

Evidence: `home_starter/server/homestarter/static/{music-runtime.js,commissioning.js,index.html,styles.css}` and `home_starter/MUSIC.md`; final synthetic captures in `screens/music-ui/`: `desktop.png`, `mobile.png`, `connection-desktop.png`, `connection-mobile.png`, `pending-desktop.png`, `pending-mobile.png`. Captures demonstrate the limited-progress UI, including explicit unverified automatic progress; the browser flow and (316) Python tests pass. Live acceptance on 0.4.8 confirmed the household API connection and audible sample; the scoped record survived a reload while automatic progress remained explicitly unverified. Existing dashboard fingerprints still matched their saved versions. Fixture names and simulated success are not design patterns or universal live verification.

### This House inspection and readiness

The optional Rooms and their equipment disclosure nests floors, rooms and equipment, reusing the same placement review controls as the exception list. Keep entity-only services distinct from hardware, with their HA reference behind a disclosure and a native entity-management handoff. Integration reports name HA's reported setup or repair evidence and offer a native review action; a connection failure does not identify a physical cause.

Household readiness is an independent read-only section with its own refresh, timestamp, text statuses and per-capability verification limits. Configuration, usable reporting and functional proof remain distinct. Source-specific review opens the relevant local disclosure or native service; unavailable evidence retains a retry action and does not block house inspection or placement corrections. These additions reuse the incumbent tokens, wrapping controls and progressive disclosure without introducing a new visual system.

Evidence: `home_starter/server/homestarter/static/this-house.js` and `home_starter/server/homestarter/house_readiness.py`; six synthetic local captures in `screens/this-house-ui/`: `desktop-house.png`, `mobile-house.png`, `desktop-rooms.png`, `mobile-rooms.png`, `desktop-readiness.png`, `mobile-readiness.png`. Desktop/mobile browser flows passed, including readiness-service failure and recovery and the native calendar handoff; (347) Python and (18) JavaScript tests passed. The changed-JavaScript detector reported no findings, and the scoped finish review returned ship. Synthetic reporting and scoped proof displays do not establish live household function.

### Household Context editor and passive wall

Household Context extends the existing administration disclosure with labeled native fields, checkboxes and selectors for date-scoped morning rules and explicit event links. Person choices use confirmed HA people; an empty selection applies to the household. Date and departure fields share the wrapping form layout. Fieldsets retain shrinking widths, summaries and checkbox labels offer (44px) minimum touch heights, and fields and actions have visible spacing. Save, discard and refresh remain explicit; refresh preserves unsaved drafts, failures retain choices, and busy requests disable controls. Source/display review opens Home Readiness. Keep calendar-source issues, current-context inspection and the separate wall-publication consent visible, including the HA state/recorder disclosure.

The wall remains native HA Sections and Markdown with a small time/date/current-conditions lead, current commitments and applicable morning rules, then chronological upcoming rows. Near commitments gain emphasis; quiet periods admit more of the next three weeks without fixed-height filler. Elapsed events leave the current list; all-day and ongoing events retain explicit labels. People and conservative leave-by times appear only from explicit links and known travel/margins. Missing or expired calendar evidence uses textual unavailable states. Reuse native HA styling and retain passive content with no generated actions, people cards or navigation; native HA chrome remains a display concern.

Evidence: `home_starter/server/homestarter/static/{context.js,styles.css}`, `home_starter/server/homestarter/{context.py,context_runtime.py,surfaces.py}`; desktop/mobile editor captures in `screens/context-ui/`. Eight fictional states were rendered on an actual disposable HA (2026.10.0) in `screens/context-native/`: `busy-morning.png`, `quiet-morning.png`, `daytime.png`, `afternoon.png`, `evening-finished.png`, `weekend.png`, `no-calendar.png` and `calendar-unavailable.png`, with additional (1280px) busy/quiet variants. Finish review covered all eight states; after a form-spacing fix and four recaptures, the scoped editor recheck returned ship. These captures establish disposable-environment visual evidence only. The household Green subsequently updated to (0.6.0) after the owner restored public repository access; real calendar/wall visual acceptance is still outstanding. Captures contain fictional data; private household screenshots and event payloads stay outside Git.

### Waste collection

Waste collection extends the existing administration disclosure beside Household Context, using the same typography, neutral borders, native controls, wrapping fields and spaced actions. Lead with Wodonga Council, collection day, next bins, service pattern and textual currentness. Keep schedule provenance in an optional disclosure. The local service preview precedes screen selection and explicit confirmation explaining the six native bin/status helpers and expiring data source. Busy actions disable controls; failures preserve the existing schedule. There is no address form or synthetic calendar content.

Selected household screens use native conditional bin context from (18:00) the prior evening until (06:00) on collection day. Quiet screens reserve no bin section; expiry does not claim collection occurred. Retained, expired or conflicting evidence keeps an honest textual status, and native helper availability expires when its source stops. Wall content remains passive. Screen selection does not replace explicit generation, review and publication of a dashboard.

Evidence: `home_starter/server/homestarter/static/{waste.js,readiness.js}`, `home_starter/server/homestarter/{waste.py,context_runtime.py,surfaces.py}` and `.impeccable/surfaces/waste-collection.md`. Fourteen fictional desktop/mobile captures in `screens/waste-ui/` cover initial, confirmed, evening, morning, stale and native HA states. The scoped finish review returned ship after an action-spacing correction; native rendering checks used disposable HA (2026.10.0). These establish implementation and visual evidence only. The household Green remains on (0.6.2); its read-only provider match did not configure or commission a household waste service.

## Do's and Don'ts

- Do preserve the incumbent admin tokens and progressive disclosure.
- Do scope AirTouch panel tokens and its photographic composition to the selected specialist overview, preserving native control subviews.
- Do distinguish reported climate activity, selected operating mode and unavailable evidence.
- Do distinguish layout preview, verified publication and native control verification.
- Do compress admitted household items into room summaries and native subviews.
- Do retain person-versus-physical-screen preference ownership and suitability explanations.
- Don't apply admin CSS tokens to native Home Assistant dashboards.
- Don't show normal-state exception sections or populate unsupported catalogue sources.
- Don't introduce control widgets or room links into generated wall content.
- Don't treat duplicate test sidebar links or simulated host chrome as Home Starter design patterns.

Evidence: `home_starter/server/homestarter/static/{styles.css,index.html,surfaces.js}`, `home_starter/server/homestarter/surfaces.py`, and final captures in `screens/v3-ui/`: `setup-desktop.png`, `setup-mobile.png`, `setup-phone-mobile.png`, `native-phone-mobile.png`, `native-specialist-desktop.png`, `native-wall-desktop.png`. Captures are local, ignored test artifacts; code remains the reproducible source of truth.

Returning-installation evidence: `home_starter/server/homestarter/static/installation.js` and synthetic captures `screens/rerun-ui/existing-desktop.png` and `screens/rerun-ui/existing-mobile.png`. Simulated host chrome is not part of the admin design system.

Home Readiness evidence: `home_starter/server/homestarter/static/{readiness.js,index.html,styles.css}`; product and verification limits are recorded in `README.md` and `home_starter/READINESS_AUDIT.md`.

Commissioning evidence: `home_starter/server/homestarter/static/{commissioning.js,index.html,styles.css,app.js}` and desktop/mobile captures in `screens/commissioning-ui/`. Product boundaries are recorded in `PRODUCT.md`; captures are local test artifacts, with code as the reproducible source of truth.

### This House commissioning evidence

This House extends Code-led Operate with the incumbent palette, system type, flat bordered sections and native controls. A compact live-facts summary and pending work lead into People, then Floors & rooms, before equipment exceptions. Healthy equipment remains optional to inspect. Disclosures retain (44px) minimum summaries; fields wrap into available columns, and physical connection or function notes use full-width labeled fields. Returning visits retain This House in the wrapping administration navigation.

Review text names the exact proposed change before an explicit confirmation. Home Assistant owns Person records, trackers, floors, areas and device placement; local household roles do not change permissions. Area purpose distinguishes an individual physical room from a room group or whole level. Physical notes record useful facts separately from placement; the explicitly reviewed Serves several rooms intent requires a physical note to explain combined coverage. Same-named records show their integration domains and an ambiguity warning. The earlier readiness questionnaire sits under Review setup with its scope explained. Saved changes use current-record checks and readback; availability alone is not proof of correct physical placement.

People also offers an optional labeled Presence choice with explicit review, preserving the incumbent controls and styling. Private intent is tied to the HA Person ID and current signature as wanted or intentionally untracked. Intentionally untracked is an accepted choice, distinct from someone who wants presence but lacks a usable tracker; Not decided cannot be confirmed. This choice does not mutate HA Person records, trackers or state, and does not infer home or away. Desktop/mobile save and reload flows and the Not decided guard passed, alongside (338) Python and (17) JavaScript tests; the scoped finish review resolved the empty-choice guard and returned ship. Green running (0.5.3) accepted intentionally untracked choices through the new UI and retained them after an actual reload. Native assigned tracker arrays, exact saved screen preferences, all published dashboard fingerprints, the original Music connection and proof, and prior house placement confirmations remained unchanged. Watch compatibility work is deferred.

Evidence: `home_starter/server/homestarter/static/{this-house.js,index.html,installation.js,styles.css,surfaces.js}` and six synthetic local captures in `screens/this-house-ui/`: `desktop-house.png`, `mobile-house.png`, `desktop-return.png`, `mobile-return.png`, `desktop-placement-review.png`, `mobile-placement-review.png`. Local browser save/reload flows passed at desktop (1280 × 900, light) and mobile (390 × 844, dark), including combined coverage, alongside (336) Python and (17) JavaScript tests. The detector ran once in degraded mode because its HTML parser was unavailable and reported pre-existing styles only; this is not a complete detector pass. Live Green acceptance on (0.5.1) confirmed household roles, floor/area creation and updates, device placements, physical notes and a native HA device rename reflected in This House. Verified Green (0.5.2) then confirmed combined coverage through a live save and reload, retaining the prior roles, structure, placement confirmations and private notes. API source reading completed. Device and entity IDs, exact existing screen preferences, published dashboard fingerprints and the private Music connection and proof remained unchanged; existing AirTouch sources remained available. This does not establish native people/tracker mutation acceptance or complete house commissioning: whole-house structure remains deliberately unconfirmed, with unresolved physical placements and trackers. Captures remain synthetic evidence; fixture records and pre-existing style findings are not new design-system rules.
