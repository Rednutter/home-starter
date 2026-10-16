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

The overview and its Climate page share the scoped navy/cyan world. Climate uses
button-card’s supported nested-card layout: the original native thermostat leads,
room controls sit alongside, and readonly airflow tiles follow. Narrow screens
stack the controls. Native card configurations, routes, Back navigation and HA
permissions are preserved. Rooms and individual rooms, Music, Today, household
context, saved people and kiosk Settings now share the specialist palette and
existing backdrop around their admitted native cards. Auto-fit columns start at
280px and shrink to the available width on narrow screens. People admission and
source configuration remain unchanged. Ambient/dark and the primary Climate
presentation retain their existing behavior. Main
climate selection prefers the admitted controller advertising fan modes. Known
offline AirTouch entities retain an inspectable native route; hidden, disabled,
excluded or audience-blocked entities remain excluded. Entity IDs are preserved.

Temperature comes from HA. Reported HVAC activity takes precedence over selected
mode; idle is distinct from cooling/heating. Unavailable entities show no invented
temperature or successful climate status. Calling and cameras remain explicitly
uncommissioned/unselected; their tiles open static setup-status pages without
calling services or camera feeds. Missing overview destinations show explicit
empty states. Today retains selected bins under their existing visibility and
expiry conditions. People are the existing saved screen people, never
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

The remaining-subpages extension now has fresh disposable native HA 2026.10.0 /
button-card 7.0.1 evidence. Docker recovered by preserving and recreating stale
runtime-only socket directories together; containers, images and settings remain
intact. The passing final stabilized native run produced 48 fresh full-page
captures across eight empty/populated pages at 1280×720, 800×1280 and 390×844,
plus 12 saved-person viewport captures across baseline/populated states. Each viewport reloads and
waits for fonts and stable geometry before capture. Native navigation, Back,
reload, kiosk viewer/admin scope, actual light toggle/restore, climate target
restore, calendar/player rendering and Play control visibility, offline/idle and bin expiry passed
in the final stabilized run. Final visual review returned **ship at native Home
Assistant fixture/browser scope**, with no remaining blocking findings, after
reviewing the weather wrapping fix, stabilized person captures at all three sizes
and the full 48-capture matrix.

HA 2026.10.0's native media-card startup `_stateObj`/`_computeProgress` exception
also reproduces on an unmodified native sections view. Matching stacks are logged
separately in ignored `.runtime/panel-native/browser-errors.json`; all other
errors fail acceptance. Browser evidence does not prove audible speaker playback,
physical tablet operation or live household publication. No new image assets or
provenance changes are introduced.

Detail styling/backdrop uses one shared button-card template to stay below HA's
4MiB WebSocket limit; an eight-person regression checks size and three embedded
images. Native card configurations retain `do_not_eval` boundaries. Native heading
cards preserve escaped titles, compact room navigation icons retain 40px sizing,
and native card radii/palette and scoped dark media fill provide continuity.

## Optional kiosk presentation

For a specialist panel, choose **Screen settings → Panel presentation → Kiosk**,
save and generate a fresh preview. Install the official HACS **Kiosk Mode** module
(tested 15.0.0) and confirm the intended dedicated display account under Physical
screen commissioning first. Missing modules, unsuitable accounts and duplicate
account display names stop the preview; publication rechecks the modules.

Kiosk applies only to that non-admin account on this dashboard. The overview fills
the viewport; control/person subviews retain HA's header and Back navigation.
The footer **Settings** link opens a native Settings view, restoring HA navigation.
It offers Profile/app settings and a **Panel mode** return. Tile/footer taps use
button-card's supported HA navigation action to stay in the Companion app. No cached global kiosk
settings or permission changes are applied. Administrator navigation stays visible.
Android's status/navigation bars remain a separate Companion app Fullscreen choice.

Old household files remain valid without the optional `kiosk` field and are not
rewritten merely by loading. Save/publication changes invalidate old physical
proof honestly. `devtools/accept_panel_native.py --kiosk` checks account scope,
settings exit/reentry, reload, full-height overview, native Back and climate control
restoration, plus readable footer labels at all four viewport sizes. Climate,
Settings and Panel mode taps must not issue browser document loads.

## Room climate and airflow

For AirTouch, exactly one admitted climate zone and damper on the same registry device are presented together. Names and entity suffixes are not pairing evidence. Each room separates its thermometer reading from a full-width native temperature adjuster, uses compact native mode icons, and shows its own readonly damper icon/bar/percentage. Accessible labels and tooltips retain explanatory wording. Missing temperature is omitted; unavailable airflow is explicit. Unmatched or ambiguous records retain their native fallback. Automatic damper control is unchanged. Six room blocks fit at 1280×720; intermediate tablets stack the system above the rooms to preserve control width.

Room panels reuse the overview photographic navy material. Names and optional thermometer readings sit beside native controls, with the damper across the bottom. No extra image assets or climate actions are introduced.
