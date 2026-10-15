# AirTouch landscape panel

The specialist overview follows the approved landscape composition: clock/date
and selected weather, a prominent Climate panel, Today, Call/Cameras, Media/Home,
and House plus saved people navigation. Generic generated room photography is
bundled with embedded provenance; no household photograph is required.

## Dependency and publication

Install **button-card** from its official HACS frontend repository. The tested
version is 7.0.1. Home Starter recognizes its same-origin module registration
through supported `lovelace/resources/list`. A missing resource retains the native
overview and gives an installation handoff in the preview. Publication rechecks
the dependency before any dashboard write. Home Starter neither downloads scripts
nor creates resources, changes auth storage, or installs a new integration.

Generate a fresh specialist preview, then explicitly publish that screen. Existing
ownership, external-edit checks and readback still apply. Phone/tablet dashboards
and household choices are unchanged. No data migration or automatic republication
occurs. A changed publication requires new physical screen verification.

## Truthful controls and context

Only the overview changes. Native climate, room, music, person and context subviews
retain their controls, routes and the viewing account's HA permissions. Main
climate selection prefers the admitted controller advertising fan modes. Known
offline AirTouch entities retain an inspectable native route; hidden, disabled,
excluded or audience-blocked entities remain excluded. Entity IDs are preserved.

Temperature comes from HA. Reported HVAC activity takes precedence over selected
mode; idle is distinct from cooling/heating. Unavailable entities show no invented
temperature or successful climate status. Calling and cameras remain explicitly
uncommissioned/unselected. People are the existing saved screen people, never
invented household members. Only admitted calendar/media/weather/light sources
appear; selected bin context requires its expiring data projection.

The layout fills landscape and compact landscape viewports, reflows on narrow
containers, and retains HA chrome. It does not implement kiosk mode, device power,
login persistence or physical screen commissioning by implication.

## Verification

`devtools/accept_panel_native.py` targets disposable HA on loopback only. It checks
HA 2026.10.0 with button-card 7.0.1 as a non-admin user: overview and native route
navigation, thermostat target increase/restoration, reload, 1280×800 and 1024×600
landscape, the actual 1280×720 viewport, 390×844 narrow rendering, unavailable climate, idle activity, selected
bin attention and expired-source warning. Captures are private ignored artifacts.
Focused Python/JS tests cover resource detection, dependency loss before writes,
source admission, native subview preservation, offline state and HTML escaping.

These disposable checks prove UI/control behavior, not physical controller
connectivity. Live HA availability and the actual panel's operation must be checked
separately before declaring the physical screen commissioned.
