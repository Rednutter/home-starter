# Household service commissioning

Home Starter keeps household people, native Persons, calendar sources, service
identities, listening progress, rooms, physical players and SIP extensions separate.
The existing dashboard shell and navigation remain the presentation layer.

## Private relationships and setup status

`/data/household-services.json` stores revisioned, epoch-scoped relationships:
native Person links; personal/shared Spotify provider-instance bindings; one Google
integration with multiple calendar mappings; audiobook libraries; endpoint health
addresses; the internal directory; and a household radio region/search vocabulary.
No account password, calendar event or raw radio stream belongs in this file.

An administrator reads/saves the strict schema through `/api/services`. Saves
require current household revision/epoch and confirmed native people. The Readiness
page displays service checks and native review links. A provider being available
does not establish playback, account ownership, registration or audible proof.

Administrators can return to **Home Starter → Service setup** at any time. The
Google section opens native HA setup, then offers the discovered integration and
calendar entities with purpose/person mappings. The Spotify section links to
native MA setup and matches planned account identities to distinct real provider
instances. The audiobook section can save a pending library name and intended
users before a provider exists. Addresses, storage locations, OAuth and passwords
are entered in the native provider setup, never in Home Starter.

Refresh preserves unsaved edits; save conflicts preserve the draft. Changed
bindings must match discovered service types, while an unavailable existing
binding is retained. These relationships are plans, not provider access grants or
verified account routing. Children retain the approved-favourites boundary.

The commissioning installation has exactly four intended Spotify identities:
two personal adult identities and two distinct shared household identities.
Children use the shared identities; they are not assigned personal Spotify accounts.
Actual names, native IDs, provider IDs and extension assignments are retained in
the private installation record, not repository fixtures. Separate shared identities
must bind to separate MA instances. Login/account switching/concurrency remain
unverified until each real account has completed native MA authentication and tests.

## Calendars

Connect the chosen Google aggregation account once in native HA Settings. Preserve
its individual calendar entities and map each to household/person/school/sport/work
or other, with explicit applicable people. Do not duplicate upstream integrations.
Bin-only calendars do not substitute for family schedules.

Readiness now accepts multiple calendar sources, verifies each selected source can
be read, and requires credible upcoming data across the selection. Context reads
all permitted, verified sources. Matching normalized title, UTC start/end and
all-day flag collapse overlapping occurrences. This heuristic cannot distinguish
two genuinely separate commitments with identical title and times. Source identity
remains part of annotation keys. Personal context requires the existing native
Person/display consent boundary plus an explicit calendar/person mapping or event
annotation. Hidden/excluded sources remain hidden. School rules retain their
existing date-scoped rule model.

## Unified media and progress

MA remains the playback abstraction. Native providers supply catalogues, and exact
HA registry IDs bind destinations to actual MA players. An administrator can add
only the zero-login `abc_radio_network` and `itunes_podcasts` sources through
`POST /api/services/provider`; Spotify and audiobook login stay in native MA.
Podcast setup uses the native HA country and excludes explicitly labelled content;
this provider filter is not a guarantee that every episode is child-appropriate.
Children receive approved House favourites and their own saved/recent choices,
not unrestricted catalogue search. Removing a personal favourite does not alter
House favourites. A House favourite is a deliberate household approval.

The radio region is installation configuration, never a hard-coded UI location.
ABC and Radio Browser supply maintainable station identities rather than scattered
stream URLs. Configured region search terms supply a cached local-radio shelf through native
MA radio search; exact home coordinates are never sent. Complete ambient category
curation and personalized Assist intents remain pending.
The existing ambient provider supplies its actual available items only.

Listener-local books/episodes, recent items, favourites, destination, delayed starts
and session sleep timers persist separately in `/data/music-listeners.json`.
Provider-global resume feedback is never imported as a person's position. Fresh
device feedback updates that listener only. Cast devices may report only a start
anchor: an explicitly requested pause, acknowledged by the same physical player
and owned queue, can capture MA's fresh frozen queue position. Stop and sleep
timers use that pause path before ending long-form playback. Each saved position
records its provenance. Ordinary running queue clocks are not imported. Native
seek offsets are confirmed before session ownership is assigned. House cannot resume a personal
session. Shared-screen person selection separates saved state; it is not
authentication of the named person. An audiobook provider's external progress synchronization needs separately
authenticated per-user libraries before it can claim provider-level isolation;
`provider_user` is deliberately rejected by the current service schema.

Audiobookshelf is a supported MA option when an actual owned library/server and
appropriate accounts are available. Do not provision an empty service and call it
working. Chapters, speed, series/author browsing, transfers and voice continuation
must be checked against the commissioned provider; they are not all implemented
by the current Home Starter listener controls.

## Pi wall endpoint

Reproducible files are in `devtools/kitchen_wall`. The inspected Pi uses its existing
desktop autologin and Wayland session. User systemd units start a dedicated Chromium
kiosk/profile and a small authenticated read-only health service. Chromium retains
its sandbox and uses a restricted HA account. The local debugging port binds only
loopback. It must never be forwarded publicly. The profile stores its HA refresh
credential and is private to the display account; it is not an administrator login.

The health endpoint accepts a dedicated bearer key, exposes no remote commands,
and returns no media metadata or HA token. Wrong authentication returns 404. Browser
health checks the configured dashboard URL and uses local CDP to confirm that the
expected non-administrator HA account is connected. It does not claim that physical
HDMI, kiosk hardware identity, power-loss recovery or an acoustic test was verified.

`/data/endpoint-connections.json` stores health keys separately (Linux mode 0600).
An administrator binds a key through `POST /api/services/endpoint`. The background
poller checks freshness/response size, prevents redirects and projects bounded,
owned `sensor.home_starter_endpoint_*` states with a 75-second expiry. Readiness
requires fresh authenticated browser health and active audio/voice services before
calling an endpoint Ready. A running browser alone is insufficient.

The inspected hardware includes USB UC02 capture/playback, Pi analogue headphones
and HDMI outputs. No purchase is needed to establish software feasibility. Actual
amplifier cabling, HDMI display connection, microphone pickup and acoustic echo
behavior require physical confirmation. Separate voice USB and music analogue
outputs are possible candidates, not confirmed wiring.

Sendspin Python CLI 8.0.0 and the OHF Linux Voice Assistant pinned source are
installed in a Pi user virtual environment. Native audio libraries and a privileged
linger/bootstrap step are still needed before activation. The supplied bootstrap
does not reboot, change sudo policy or enable unattended OS upgrades. Hey Jarvis
models are available upstream. Assist pipeline enrollment, HA microphone control,
playback/grouping and wake/action tests remain commissioning work. Do not mark
microphone/voice/audio ready from installed packages alone.

## Calling and credential isolation

Reuse the existing Asterisk add-on and internal dialplan. The private directory
retains the requested six household extensions independently of people/devices.
Each new extension has its own random SIP secret; existing automatic extensions
remain until replacement clients are registered and tested. No trunk is required.
PBX configuration is not registration or extension-to-extension call proof.

The inspected SIP Core HTTP view returned all configured SIP users to any
authenticated HA account and logged configuration options. The narrow compatibility
repair in `devtools/sip_core_credential_scope.py` limits responses to the exact
signed-in HA user ID, removes shared backup credentials and configuration-value
logging, and preserves the directory. It intentionally does not match display
names. It requires a private backup and HA restart; HACS replacement may remove
the repair, so recheck after updates. Do not add shared fallback passwords to work
around missing client bindings. Legacy PBX-generated shared credentials need a
separate client migration/rotation once their consumers are identified.

Home Starter's existing call UI still needs real registered endpoint/action/state
bindings. Planned directory records alone do not enable a Call button.

## Recovery, addressing and evidence

Prefer router DHCP reservations for the Pi, HA/PBX, AirTouch and fixed endpoints.
Keep hostnames where supported; a successful DHCP lease is not a reservation.
Do not alter network settings without the actual router mapping. Record the Pi's
Wi-Fi and Ethernet MACs privately because they differ.

Inspect user services with `systemctl --user status home-starter-display
home-starter-health`; restart only the affected service. Audio/voice have separate
recovery requirements. Never clear the Chromium profile to fix connectivity unless
prepared to log in again. Refresh expired Home Starter ingress sessions normally.
Restore PBX/custom integration changes from the private commissioning backups if
their readback or startup check fails; preserve existing endpoints during rollback.

The local ignored `.runtime/household-commissioning/` directory contains live
inventory, relationship mappings, version/update evidence, display screenshots,
native integration backups, dedicated wall credentials, SIP credentials and health
key configuration. Treat the whole directory as private, not as a report to share.
HA/MA account passwords and OAuth tokens remain in their native services. The
existing owner API credential remains in the user's local MCP setup and is never
installed on the wall Pi. The Pi's private profile/config live under its display
account's `.local/share/home-starter` and `.config/home-starter` directories.

Remaining owner inputs: calendar hub account/authentication, four Spotify native
sign-ins, real audiobook server/library and listener bindings, router reservations,
physical screen/audio confirmation and privileged Pi bootstrap. Validation must
distinguish software-reported playback from human audible confirmation and actual
hardware reboot/power-loss evidence. Pending updates are inventory findings, not
permission to enable unattended upgrades.
