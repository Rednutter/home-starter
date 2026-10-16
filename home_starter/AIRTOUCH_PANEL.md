# AirTouch household page system

The approved House dashboard is the visual foundation. Its asymmetric six-card
composition, time/date/weather, neutral charcoal ground, photographs, directional
overlays, white Roboto and restrained blue selection/operation accents are retained.
The focused pages extend that world; they do not use generic HA entity pages.
Decorative bundled photographs never imply real household devices or camera feeds.

## Pages and navigation

Primary navigation is **House + configured household people**, in saved order.
No reference-image family names, portraits or sample capabilities ship.

| Surface | Purpose |
| --- | --- |
| House | Existing glance dashboard; tap a feature to focus it. |
| Today | Actionable lead commitment and up to six later briefing rows. |
| Call | Commissioned destinations, incoming call or simplified active-call state. |
| Cameras / Door | One selected camera, selectors and explicitly supported entry actions. |
| Media | Current shared playback, transport, permitted destinations/grouping and volume. |
| Home / Rooms | Actual areas with concise live state, then useful room controls. |
| Person | Own rooms, listening destination, scoped Today, permitted shared controls and family shortcuts for adults. |
| Person focused pages | Named personal Today, Media, Call, Cameras / Door, Rooms and context routes. |
| Ambient / Dark | Manually entered display states with Active/Wake return and safety alerts. |
| Settings | Secondary display utility with Profile/app settings, Panel mode and Exit panel. |

Every focused route has an explicit Back target. Room Back returns to its owning
Rooms view; personal feature Back returns to that person. A House shortcut appears
on deeper routes. Household navigation stays available except in Dark. Navigation
uses button-card's supported HA action helper and remains within the Companion app.
Direct loading and reload use the same explicit routes.

## Shared shell and controls

`panel_pages.py` generates routes, one shared `home_starter_page` template and a
compact per-House/per-person source registry. `panel-shell.js` supplies status,
header, safety and navigation; `panel-pages.js` supplies feature-specific content.
`panel-pages.css` extends the exact approved House CSS and bundled imagery.

Focused cards retain the 24px feature radius, slate borders and neutral surfaces.
Headings use 26/24/22px; body uses 20px and secondary copy 18px. Controls have 56px
minimum dimensions and explicitly bounded icon hosts. Keyboard focus stays visible.
Personal landing availability summaries are compact; richer setup/control surfaces
belong on their focused routes. Personal headings identify the configured person.
Chronology follows the Today headline rather than becoming a separate eyebrow.

Room controls reflect actual HA features: light toggle/dimmer, fan speed, climate
mode/target, normal blinds and speaker navigation. Security/entry devices remain
status-only here. The developed main Climate experience retains native thermostat,
zone and airflow semantics inside the shared neutral shell, with `do_not_eval`
protecting native card configuration. House itself is not redesigned.

Shared and route metadata are JSON strings parsed inside the renderer. This keeps
household labels inert to button-card's recursive template evaluation. Text is HTML
escaped. Registry sharing and one embedded image set per shell keep the eight-person
dashboard below HA's 4MiB message limit.

## People, rooms and permission boundaries

People own context and listening identity. Rooms and players are shared physical
destinations. Selecting a person on the shared wall does **not** authenticate them.
HA remains responsible for signed-in user permissions and service execution.

Existing Home Starter admission, source choices, hide preferences and audience
rules still apply. Explicit member rooms/devices establish child controls; a
bedroom speaker is the default output, not a hard restriction. Other expressly
permitted players can be selected without starting playback. Parents can open
configured child views; this is shared-panel navigation, not privileged sign-in.

Personal Today requires an explicit, uniquely confirmed native Person link through
the existing selected presence source. Personal calendar events/rules are filtered
by that native identity. Missing links show an empty personal briefing; House is
never copied into every person's feed. See [Household Context](HOUSEHOLD_CONTEXT.md).

## Commissioned capability contract

Home Starter owns commissioning. AirTouch reflects it and stores no parallel
provider setup or listener database. The current readiness policy does not yet
produce call, camera-entry or personal-listening adapter bindings. Those pages
therefore remain setup states in ordinary generated dashboards. Their UI contracts
are implemented and tested with fictional owned projections, not live integrations.

A future commissioner can provide a ready revisioned `panel_bindings` entry in the
existing generation policy, scoped to House or a person. Existing Wanted intent
and selected screens still gate it. It names an owned sensor projection and explicit
service descriptors; the UI checks surface, epoch, person, feature, revision,
freshness and registered service support before rendering/dispatching actions.
Raw discovery, an entity name or a person tab never proves capability readiness.
Credentials do not belong in this metadata.

Call supports idle destinations, incoming Answer/Reject and active duration/Mute/End.
The active state replaces the destination grid. Cameras show only selected sources;
Talk needs a declared supported action. Open additionally requires an explicit
camera/entry association, a current event and permission for the actual HA user.
Dismiss returns to camera selection. No camera/lock relationship is guessed.

Personal listening can represent independent audiobook positions, Mine/Shared/House
choices, delayed starts/countdown/cancel/start-now and sleep timers. Services own
scheduling and progress: rendering or selecting a destination never starts audio
or advances a book. Actual provider producers, persistence, Music Assistant wiring
and household loudness calibration remain commissioning work. Native player volume
is explicitly labelled as the speaker's own scale. See [Music](MUSIC.md).

## Publication, kiosk and lifecycle

The installed same-origin HACS **button-card** module is required (tested 7.0.1).
Missing resources retain the native fallback and an installation handoff. Preview
and publish retain ownership, external-edit, dependency and readback checks.
There is no automatic resource installation, authentication change or migration.
Publish each screen explicitly after a fresh preview; publication is not physical
screen verification. This page-system task does not deploy or publish to the Green.

Optional specialist `surface.kiosk` uses the installed **Kiosk Mode** module
(tested 15.0.0) and a validated, uniquely named dedicated non-admin display account.
For that viewer, all owned routes hide HA chrome consistently, including Ambient,
Dark and Settings. Settings preserves Profile/app settings and **Exit panel** to
HA Overview with `disable_km`; HA navigation becomes available outside the owned
routes. Administrators, other accounts and other dashboards retain their chrome.
This supported presentation choice avoids installing a global theme or mutating
account appearance. It does not change permissions or enforce a startup URL.
Android system bars and Companion fullscreen remain physical-device settings.

Ambient/Dark are manual states. Automatic inactivity transitions, event takeover
from another route, wake/return coordination, device power and app startup/default
dashboard remain separate work. Incoming call and door event UI states are ready
inside their focused pages; no background call or doorbell coordinator is claimed.

## Verification and release scope

Started from `main`, 0.8.12, commit
`13be2ad4b80d653ea7d5fbaecda6cd1d8e99d9b0`. Version 0.8.13 is local page-system work.
The earlier Green publication is not altered by these repository changes.

`devtools/accept_panel_pages.py` is the current disposable-HA acceptance driver;
`accept_panel_native.py` records the earlier native-detail implementation. The new
driver covers focused routes, direct reload, Back, Settings escape, bounded icons,
touch targets and overflow at 1280×720, 800×1280 and 390×844. It includes empty and
populated scoped Today, a six-zone Climate layout, and actual fixture light and
thermostat actions followed by restoration. Capture files and credentials stay
ignored/private. Browser errors fail acceptance; the custom Media page avoids the
previous upstream native media-card startup exception.

Python/JS regressions cover admission, shared/per-person context isolation,
projection ownership/expiry, child default and alternative destinations, separate
listening/progress, service failure, grouping, call/camera action guards, Dark safety,
HTML/template boundaries, retained native Climate configuration and message size.
Fixture/browser evidence does not prove live audible playback, camera/call services,
physical AirTouch operation or household commissioning. Final test/review counts
are recorded with the delivery and design-system evidence.
