# Household acceptance and shortest safe completion path

Current assessment: 23 October 2026. This is the current M/A/W matrix; older session
notes remain historical evidence. No acceptance test below is WORKING. Synthetic
passes establish local contracts only. No deploy/restart/install/control/cutover
approval has been inferred from this audit.

## Evidence

- **L1:** Authorised native HA/MA reads: MA 2.10.7 started; native reads work, but
  earlier current-session Home Starter guard/media commands returned HTTP 400.
  Installed source bytes remain unverified; the console hash procedure is pending.
- **L2:** Fresh HA Lovelace read of the managed AirTouch dashboard: 85 views, House
  present, existing shared template. Entire local panel-layout.css is embedded
  unchanged. This proves saved deployment configuration, not physical rendering.
- **L3:** Fresh radio read: three idle Triple M queues have correct catalogue/queue
  labels, no stream title/artist. AirTouch has no stored session. Available 100 MA
  log lines contain no asset cue or radio metadata; photographed cause unreproduced.
- **L4:** Earlier session inventory: Kitchen Hub and Pi analogue Living Area output
  available; legacy Kitchen Chromecast Audio and Flynn Mini unavailable. Other
  endpoint states are dated in HOUSE_COMPLETION.md, not freshly re-probed here.
- **L5:** Six household MA users; Grant/House/House #2 Spotify connected, Renae
  pending authentication. Children have no Spotify identities. Oct18 allocator
  success is historical and does not establish current enforcement after update.
- **L6:** Earlier read-only audit: seven climate entities unavailable; saved enabled
  controller address .135, discovered AirTouch 5 protocol .124:9005 reachable.
  That is not independent discovery of the Android dashboard address.
- **L7:** Existing Libation files found; ABS not configured. Docker/Compose installed,
  engine stopped at the earlier inspection. No server/install/account was created.
- **T1:** Fresh post-edit full suite: 989 Python, 102 JavaScript; Ruff lint/format,
  privacy and diff checks pass. New camera/ingress/uncertain-response tests included.
- **T2:** Fictional loopback browser checks pass at 390/820/1440 pixels, including
  profile switching, focus, query results, delay state and failure/ownership flows.
  Isolated connections browser checks pass. Neither is physical-device acceptance.
- **T3:** Local station recipes, scoped preview feedback, repeat/context ranking,
  source-failure isolation and two-person same-book progress routing tests pass.
  Proposals are not accepted playback/history; real station execution is unfinished.
- **T4:** Isolated template tests: MA read deadline includes ingress/parsing; malformed
  or wrong-person/epoch lists fail closed; camera deadline/retry/stale events do
  not set command pending or change a departed route. Disabled Call has no callable
  controls. Fresh empty Today is distinct from unavailable/partial sources; missing
  room readings never become numeric sliders/current climate values. Person speaker
  summaries follow shared-service availability; unavailable camera Talk is blocked,
  and repeated in-flight provider taps issue one command. Native Lit/button-card and physical AirTouch behaviour remain untested.

- **T5:** Separate view-only preview preparation/verification passes synthetic config
  and Chromium checks. 59 generated fields and 331 event-handler checks, plus real
  keyboard link activation, reached zero service/network spies; browser requests
  were blocked and none attempted. Native controls become read-only summaries.
  No preview was published; this does not prove live rendering or control.

## External prerequisites

- **P1:** Existing HAOS console operator returns three source hashes (separate ignored
  RADIO_READONLY_HANDOFF.md). Read-only; no repair/restart. Missing route is
  unavailability, not denial. No uncertain live execution exists.
- **P2:** Explicit approval/window to restore reviewed MA enforcement and restart MA
  only. New radio candidate and new station/queue security adapter need separate
  compatibility review and deployment approval; the original staged bundle is immutable.
- **P3:** Approval to deploy the coherent app slice to the existing authenticated
  service for isolated real-device tests. No new port/default family entry point.
- **P4:** Backed-up AirTouch config correction/Core maintenance approval, identity and
  zones checked before an exact existing-entry host edit. Preserve entity IDs;
  HVAC control tests require household-impact checks and an operator/observer.
- **P5:** ABS engine/start/install approval; inspect existing containers first.
  Initially localhost-only with read-only books. LAN reachability, local accounts,
  credentials and per-user native provider mappings require separate approval/setup.
- **P6:** Renae's own secure native Spotify authentication and any matching upstream
  backend steps; no credential creation/copy, accepted terms or Google access inferred.
- **P7:** Controlled listening window, agreed destination mapping and endpoint recovery.
  Pi mic permission exists for short local tests, not queue replacement or all-room proof.
- **P8:** Actual phone/PC/AirTouch and a non-builder observer for readability, wake,
  navigation and family-use acceptance. No screenshot/API result substitutes for this.
- **P9:** Preserve the current AirTouch display layout and visual approach, per the
  latest owner direction. Select the few Google routines to replicate, then agree full cutover explicitly
  only when nearly complete. Preserve existing defaults and avoid duplicate triggers.

## Music acceptance

| Test | State | Evidence | Remaining implementation / external prerequisite |
| --- | --- | --- | --- |
| M1 Kitchen playback | BLOCKED | L1/L4, T2 | Resolve amp/Pi versus unavailable Chromecast target; P2/P3/P7/P8; audible UI test. |
| M2 independent child room | BLOCKED | L4/L5, T1 | Recover missing endpoint; P2/P7; prove no Kitchen interruption. |
| M3 shared contention | BLOCKED | L1/L5, T1 | P1/P2/P7; prove House -> House #2 -> Grant, busy/personal priority and Renae exclusion. |
| M4 radio | BLOCKED | L3, T1/T2 | P3/P7/P8; direct Triple M UI playback, receiver title and no Spotify allocation. |
| M5 ambient | BLOCKED | Live free-source catalogue, T1/T2 | P3/P7; audible free stream, account occupancy and stop/timer. |
| M6 podcast | BLOCKED | Live podcast source, T1 | P3/P7; find show/episode/room, play and resume without admin. |
| M7 audiobook | BLOCKED | L7, T3 | P5/P3/P7; per-person backend integration and same-book independent progress. |
| M8 Renae isolation | BLOCKED | L5, T1 | P6/P2/P7; personal playback works while shared allocator never selects her. |
| M9 recovery | BLOCKED | T1 only for state contracts | P2/P4/P7; approved HA/MA restarts and selected-player outage/recovery, then audible retest. |
| M10 family UI | IN PROGRESS | T2/T4 | Finish core gaps below, P3/P8; normal playback must avoid MA administration. |

## AirTouch acceptance

| Test | State | Evidence | Remaining implementation / external prerequisite |
| --- | --- | --- | --- |
| A1 climate | BLOCKED | L6; native control source retained | P4/P8; safe on/off, setpoint and all six zones on actual console. |
| A2 Today | IN PROGRESS | L2; verified/stale-context tests | P8; current selected commitments/weather and glance clarity; honest missing data. |
| A3 Media | IN PROGRESS | T1/T2/T4, shared Listening API | P2/P3/P7/P8; Kitchen/child play, volume, pause/stop and accurate metadata. |
| A4 person pages | IN PROGRESS | L2 deployed routes; navigation tests | P8; all five people and House reachable in one bottom-nav tap. |
| A5 cameras | IN PROGRESS | Earlier four Ring entities available; T4 | P3/P8; useful actual image/view; native load/error handling and Eufy availability unresolved. |
| A6 failure isolation | IN PROGRESS | T4 | P3/P8; real unavailable/slow service leaves remaining cards/navigation usable. |
| A7 reload/wake | BLOCKED | L2 saved configuration only | P4/P8; real HA/browser/device recovery and reliable idle/wake; no permissions changed. |
| A8 family test | BLOCKED | No non-builder acceptance | P8; near-complete cohesive experience, then P9 cutover decision. |

## Dedicated web/PWA acceptance

| Test | State | Evidence | Remaining implementation / external prerequisite |
| --- | --- | --- | --- |
| W1 cross-device | IN PROGRESS | T2 | P3/P8; real phone, AirTouch and PC; PWA/device support still unverified. |
| W2 profiles | IN PROGRESS | T1/T2/T3 | P2/P5/P6/P7; six profiles, correct native user/source and independent progress. |
| W3 unified search | IN PROGRESS | T1/T2/T3 | Protected Spotify query bridge, broader pagination/book sources; P2/P5 and representative live searches. |
| W4 playback | BLOCKED | T1/T2; L1 | P2/P3/P7; selected content actually audible at selected room. |
| W5 queue | IN PROGRESS | T1/T2 | Spotify-safe additions and large-queue support incomplete; P2/P3/P7; real next/reorder/remove. |
| W6 transfer | IN PROGRESS | Isolated finite transfer/owner/position/timer/recovery tests | Separate pinned native candidate prepared, uninstalled; P2/P3/P7. Spotify, scoped sources, books/podcasts and groups remain unavailable. |
| W7 multi-room | IN PROGRESS | T1/T2 ownership/overview | P2/P3/P7; independent active sessions and safe per-room controls. |
| W8 timer | BLOCKED | Existing backend, T1/T2 | P3/P7; prove audible stop and visible cancellation/recovery. |
| W9 child playback | BLOCKED | L5; restriction/allocator tests | P2/P7; real shared-pool playback without child Spotify accounts. |
| W10 parent control | IN PROGRESS | T1 session ownership/person routing | P3/P7/P8; parent observes/stops actual child playback safely. |
| W11 podcast resume | BLOCKED | Native podcast available; local routing tests | P3/P7; independent real episode progress/resume. |
| W12 audiobook resume | BLOCKED | L7/T3 | P5/P7; two people resume the same book at different positions, with backend sync. |
| W13 radio | BLOCKED | L3/T2 | Same gap as M4; receiver metadata candidate requires its own review. |
| W14 ambient timer | BLOCKED | Free catalogue/T1/T2 | Same gap as M5 plus actual timed stop and no Spotify occupancy. |
| W15 Spotify contention | BLOCKED | L1/L5/T1 | P1/P2/P6/P7; native occupancy, concurrent starts, empty/reconnect maps and Renae isolation. |
| W16 context | IN PROGRESS | T3 deterministic weighting | Connect real accepted history/context where known; P3/P8; morning/night and explicit request tests. |
| W17 radio from song | BACKLOG | Text/seed preview planner only | Implement item-seeded, account-pinned evolving playback and accepted-history repeat control. |
| W18 genre/era radio | IN PROGRESS | T3 recipe previews | Reviewed protected execution bridge/continuation missing; P2/P7 live relevance/evolution test. |
| W19 steering | IN PROGRESS | T3 scoped preview feedback | Wire feedback to actual queue continuation; P7 verify future selections change. |
| W20 saved recipe | IN PROGRESS | T3 persistence/regeneration | Actual station restart must regenerate a fresh playable queue; P2/P7. |
| W21 Keep It Going | BLOCKED | Capability gate prepared; L1 | P2/P7; native end-of-queue test; new recipe feedback not connected. |
| W22 presets/groups | BACKLOG | Native membership/capability inventory | Implement explicit approved presets/group operations; P7 sync and individual/group volume tests. |
| W23 this browser | BACKLOG | Capability-dependent native endpoint only | Implement supported MA browser endpoint/session path; P3/P8; no new identity/access inferred. |
| W24 recovery | BLOCKED | T1 local persistence/auth tests | P2/P4/P7/P8; real reconnects, pin/filter integrity, timers and profile progress survive. |

## Layout reconciliation

Fresh saved deployment and local source both use the following landscape areas:

```text
Climate | Today | Today
Climate | Call  | Cameras
Media   | Home  | Home
```

Column weights are 2:1:1. A narrower-container rule instead stacks Climate, Today,
Call/Cameras, Media, Home. Actual Android viewport/rule selection is unverified.

The owner handover agrees on Climate upper-left and Today upper-right, but asks
for smaller Home/Media middle cards, wide Cameras lower-left and Call lower-right.
The latter placements differ from deployed configuration. The same deployed rules
are present in the archived Oct17 configuration; commit 29310c2 introduced them
on Oct15 and 13be2ad retained them on Oct16. AIRTOUCH_PANEL.md calls the existing
six-card composition approved, but does not supply an owner image resolving the
newer positional brief. The wall's Smart Family Morning reference is a different
surface and must not be substituted. Subsequent explicit owner direction resolves this difference: the current AirTouch
layout is good as it is. Preserve its geometry and visual approach, finish the pages
behind the cards and rationalise displayed information. The older handover's
positional arrangement is superseded; no rearrangement is planned. No physical screenshot or family acceptance
is inferred from this configuration comparison.

## Shortest safe sequence

1. Combine the read-only MA hash check and, only if separately approved, the staged
   repair in one HA Green console visit. Stop on mismatch. Verify adapter/pins,
   six users/four intended identities, source restrictions and existing leases.
2. Finish the concrete missing native core locally: protected catalogue/station and
   Spotify queue bridge, transfer/session handoff, usable grouping/presets and the
   supported browser endpoint. Review each security-sensitive adapter separately;
   do not change the staged restoration archive or silently enable presets.
3. In agreed maintenance windows, repair AirTouch's existing entry with backup and
   preserved IDs; complete approved ABS setup/limited reachability/per-user sources
   and Renae's own login. These approvals are independent of household cutover.
4. Deploy a coherent isolated app slice through existing authenticated ingress,
   keeping family defaults intact. Use one planned listening session to test basic
   Kitchen audio, direct radio/ambient and receiver metadata, then independent rooms,
   allocator contention/Renae isolation, queues/transfer/groups and timed stops.
   Test two-listener same-book/episode progress with real backends.
5. In approved windows test HA/MA/player outage/recovery, re-read pins/filters/leases
   and repeat audible tests. Verify real AirTouch climate, Today, cameras, failure
   handling and wake/reload, preserving the current layout and visual approach.
6. Have a non-builder use the almost-complete phone/PC/AirTouch experience without
   instruction. Compare ordinary speed, playback, queues, handoff and metadata with
   the existing Nest/Spotify baseline. Only then agree selected Google routine
   migration and a full cutover, avoiding duplicated triggers. No Google account
   access, replacement defaults, or cutover is authorised by this sequence itself.


## Latest bounded local work

W6 now has review/confirm/recheck UI shared by web and AirTouch, a durable journal,
room occupancy and native-user revision checks, queue/position/owner proofs,
unchanged sleep deadlines and quiet paused-queue staging. Unknown outcomes block
only the affected pair, preserve the journal/timer and inspect rather than resend;
a timer may run late until room ownership is proven. Other profiles' book progress
is untouched. A separate uninstalled ma_transfer.py candidate reuses MA's native
transfer under native player locks, restores requesting context and preserves the
queue userid missing from the upstream operation. It requires exact 2.10.7 source
pins and existing USERS_MANAGE scope; it creates no credentials or permissions.
Native clients' unrelated edits are not a universal transactional guarantee.
Spotify/account leases, profile-scoped catalogue and audiobook/podcast transfer
remain unavailable until their enforcement/progress adapter is reviewed.

AirTouch card summaries now distinguish unknown from off, reject expired calendar
entries, consume fresh matching House projections and reject technical cue titles.
The Media page favours the shared service's owned-session title. Climate controls,
Home room controls, Camera timeout/retry and honest disabled Call remain. Current
layout/styles/person navigation/entity IDs are preserved. These are undeployed
local changes; native-device and family acceptance remain external prerequisites.
