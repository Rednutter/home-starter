# Household music and AirTouch completion board

Current live web deployment: Home Starter **0.8.40** on HA Green, verified 23 October
2026 from release `d868b7bf3fb5975189a3149bbdcb59a82b6b2c41`. Open the existing
Home Starter HA ingress page, then **Open Household Audio**. The authenticated
web interface renders; playback/family acceptance is still outstanding. Earlier
blanket deployment-hold notes below are historical: this service update/restart
was explicitly approved. MA repair, climate maintenance, ABS, preview publication
and household cutover remain separately gated.

Latest design direction: preserve the current AirTouch layout and visual approach;
finish card destination pages and rationalise information. Older geometry
reconciliation notes below are historical and superseded, not an open redesign.

Current acceptance status: [M1–M10, A1–A8 and W1–W24 matrix](HOUSE_ACCEPTANCE.md).
This matrix supersedes older acceptance summaries below; session notes are retained
as dated evidence. No synthetic result is marked WORKING.

Live audit began 22 October 2026; board updated 23 October 2026. Player inventory
retains the earlier availability observations. A fresh reduced radio-metadata read
on 23 October found no playing MA radio queue; Master external ocean sounds were
playing and left untouched. Idle radio queues retained the correct station name. This is a commissioning record,
not a release or a claim of physical acceptance. Music and the added Priority 1B
Household Media web app precede AirTouch. Existing pending approvals remain pending.

Authoritative context: the owner-supplied mission and current AGENTS.md, with
[the household Notion specification](https://app.notion.com/p/3f96b9a3dd6c81d084ffe2e21dfa64a6).
Its original no-Grant-overflow wording was superseded by the later explicit
House → House #2 → Grant allocation instructions and its dated delivery update.
No Google account access is permitted. Existing speakers are read through HA/MA.

## WORKING

These are narrowly verified live capabilities, not completed playback tests.

| Capability | Fresh evidence |
| --- | --- |
| HA Green API | Authenticated state/registry/dashboard reads; HA 2026.10.2 running. |
| Music Assistant inventory | Native provider/player/queue/user reads; installed MA 2.10.7 started. |
| Existing identities retained | Six intended MA users found once each; pre-existing Party Guest preserved. Grant, House and House #2 Spotify providers available; no child providers created. |
| Household catalogue browsing API | Published AirTouch surface returns category buckets, five free ambient choices and room choices. This does not establish successful playback or physical touch use. |
| Retained non-Spotify radio catalogue | Eight native saved radios read with pagination, including Triple M The Border 105.7 and hit 104.9 The Border, both mapped to `builtin`. Two saved podcasts and zero native audiobooks read back. Playback remains untested. |
| Pi microphone measurement path | Existing `kitchen-wall` UC02 Mono USB input captured 2.985 seconds locally, returning only RMS -37.7 dBFS and peak -19.8 dBFS plus level windows. Raw audio discarded in Pi memory; no playback, gain/mute or voice setting changed. Audio and voice services remained active. Acoustic energy does not identify the source, prove music audibility, speaker sync or family use. |

## IN PROGRESS

| Work | Current result / next step |
| --- | --- |
| Restore managed music | Reviewed MA sources compiled and bundled. Three non-secret repair files staged on the existing HA Samba share with byte-for-byte readback; no adapter execution/install/restart. A check-first operator script validates bundle hash, upstream digest and reviewed version. Existing HAOS console execution is the smallest identified path. |
| Truthful Media failure state | Source fix hides Surprise Me/continuation controls when protection is unavailable and shows a generic temporary message. Renae's missing personal provider does not advertise shared discovery. Browsing/free-audio choices remain. Recovery and no-transport regressions pass; not deployed. |
| Household Audio web core | Responsive web shell and generic PWA manifest at the existing authenticated service's media route. Same ListeningRuntime/API, allocator, profiles, timers and progress; no new engine, port, guest grant or credential store. Profile/browser preferences are opt-in opaque IDs. Synthetic phone/tablet/desktop, no-auto-play, escaping and auth-failure tests; not deployed. |
| Queue ownership, edits and takeover | Prepared common service/web/AirTouch flow exposes checked owner/queue, Join/Leave, supported Add/Play Next and owner Up/Down/Remove. Current/buffered audio is protected. Source, version, ownership and revision checks reject unsupported/stale operations. Review/Confirm takeover expires after 30 seconds and transfers only a supported non-Spotify music queue's household control; queue/playback state and personal progress stay intact. Its old session timer is cleared explicitly; other rooms' timers remain bound. Spotify/progress-source edits/takeover and child takeover are unavailable. Local tests only; not deployed. |
| Station recipes and preview planning | Prepared per-profile saved recipes, deterministic seed/genre/era/context weighting, upstream-ID track/artist repeat limits, More/Less/Never at preview-session/station/profile scope and explicit scoped reset. New previews re-search and regenerate; recipes do not save a static playlist. Sparse results/failures retain restrictions. Web UI labels proposal queues as previews and reports coverage across explicitly assigned, declared-capable non-Spotify sources. No playback bridge, native history ingestion or automatic presets. Existing Keep It Going now requires guarded pinned-source capability. Not deployed. |
| Audiobook UI context and progress routing | House book links and web profiles select the same person context. Prepared native ABS playback requires one explicit person/source, matching native user, exclusive nonempty filters and reviewed MA 2.10.7. Required native-user propagation and exact source URI are passed to MA; native resume is preserved. Synthetic same-book tests keep two listeners at 123/907 seconds and reject empty/deleted/shared mappings before transport. Not deployed; no live ABS isolation claim. Spotify reconciliation no longer automatically shares progress providers and preserves existing explicit assignments. |
| AirTouch address repair | Standard information-only discovery returned exactly one AirTouch 5 at 192.168.68.124; TCP 9005 reachable. Earlier saved .135 and disabled .129 both time out on 9005. Device identity/zone confirmation and a safe existing-entry host update are prepared; no entity recreation or HVAC command. |
| Published touch dashboard | Live configuration includes House, all five person pages and required feature routes; Home Starter 0.8.39 started. Configuration readback does not establish family use. |
| Commission audiobooks | Existing accessible Libation media: 88 M4B + 106 MP3 files, 45.52 GiB; file counts are not title counts. No configured ABS URL/token, Home Starter library or MA audiobook provider. Official pinned 2.37.1 Compose proposal validates locally, with read-only books, separate persistent volumes and localhost bootstrap. Nothing installed or started. |

## BLOCKED

| Item | Exact evidence / action required |
| --- | --- |
| M1: Kitchen playback | Historical `media_player.the_kitchen` is now Kitchen Hub, a Google Nest Hub. The actual Kitchen Speaker Chromecast Audio is unavailable. Living Area Speakers is the existing Pi/analogue-amplifier alternative, available and idle. Confirm intended destination and test audibly from UI without renaming IDs. |
| M2: independent child audio | Kitchen/children's Cast devices report Spotify activity; master bedroom reports relaxing-sounds activity. Preserve these native sessions. A suitable listening window and someone at the speakers are required. Flynn's Mini is also unavailable. |
| M3: shared Spotify allocation | Live connections report protection incomplete. `homestarter/account_status` and `homestarter/media_status` return MA HTTP 400, while ordinary reads succeed. Restore the reviewed adapter before shared playback; do not broaden filters or bypass protection. Prior 18 October tests are historical evidence only. |
| Station playback / catalogue coverage | New recipes currently generate previews only. No non-Spotify track-search source has been verified live for them. Spotify recipe planning is deliberately blocked because the reviewed adapter lacks the recipe/feedback protocol; it needs a separately reviewed bridge inside the sole allocator before real station queues/continuation can enforce saved exclusions. The current staged security repair remains unchanged. No broad catalogue, evolving playback or native listening-history claim. |
| Adapter deployment | Former maintenance key absent and port 22222 refuses connections; this is unavailability, not an approval denial. All installed management add-ons were inspected. MA stdin=false; Node-RED, File editor, Home Starter and Asterisk lack Docker access. Supervisor can restart MA but cannot execute its installer. Needs operator execution on the existing secure HAOS console; a new agent access mechanism would require explicit approval. No credentials generated, access enabled or protection disabled. MA auto-update is currently true; it was not changed silently. |
| M4: MMM The Border | Managed media API fails while the adapter is absent. Native Triple M The Border 105.7 still exists, mapped to `builtin`, with no Spotify mapping. Restore adapter and test UI → chosen speaker → audible radio without Spotify. |
| M5: ambient | Five native free ambient choices are returned, including Rain, Brown noise, White noise, Pink noise and Ocean waves. Fresh audible play/stop and account non-consumption tests await the listening window. |
| M6: podcast | iTunes Podcast Search provider available. Full episode selection, chosen-room playback and resume acceptance await the listening window. |
| M7: audiobook | Docker/Compose installed but Linux engine stopped, so existing containers/images cannot yet be inventoried. Proposal: start existing engine, inspect for an existing server before pulling official 2.37.1, localhost setup, then separately approved 192.168.68.121:13378 binding/HA-only firewall if needed. Local ABS root/listener identities and exclusive native provider assignments need explicit consent and native setup. Per-user routing is now prepared and locally tested; real native progress sync/recovery remains unverified. No new software/service/account/security changes made. |
| M8: Renae | Existing MA user present; Spotify provider remains ready for authentication. Requires Renae's own native sign-in. Never use her for overflow; no account access attempted. |
| M9: recovery | HA/MA restarts withheld during current household playback. First restore the adapter, arrange a test window and verify player recovery and persistence. A successful restart alone will not establish audible success. |
| M10 / A3 / A8: family use | Computer Use has no exposed browser; in-app creation unavailable and lookup by actual dashboard URL also returned no browser. Opening through the Codex panel was queued until the local task is shown. This is a current tool route limitation, not proof the physical console cannot be tested. Actual tablet and non-builder acceptance still require an observer. No emulated/API test counts as family acceptance. |
| A1: climate | Whole-system and six zone entities unavailable because enabled entry retains .135; discovery now identifies reachable protocol service .124. Correct port is 9005; earlier 9004 probe corrected. This is not independent proof of the Android UI's address. Native config flow lacks reconfigure support. Existing Node-RED has Exec plus Supervisor manager role and a declared writable HA config mount; its authenticated APIs were read only. A fixed independent backup/stop/one-field-update/start job is a candidate avoiding new access, subject to runtime preflight and pending approval. Native backup, same IDs and exact one-field diff are required. Do not edit live storage or recreate the integration. No HVAC commands. |
| A2: Today | Routes exist; physical readability and current-data glance acceptance remain untested. No calendar consent or visibility changed; no private events exported. |
| A4: person navigation | Five person routes read back from deployed configuration. One-tap navigation on the actual console remains untested. |
| A5: cameras | Four Ring camera entities idle/available; three other camera entities unavailable. No live-view or snapshot is claimed from entity availability. Actual tablet view/loading test remains required. |
| A6: failure handling | Synthetic failure regressions pass; unavailable climate/media are observed live. Actual tablet containment/readability remains untested. |
| A7: restart/wake/idle | Companion entities exist; most display/activity diagnostics are disabled by the integration. No permissions enabled. Actual wake-on-touch, idle and browser/device recovery still need console observation. |
| Group synchronisation | Earlier owner explicitly reported unresolved sync. Existing Pi microphone now supplies a verified short local measurement path; it has no evidence of hearing every room. One passive capture cannot establish sync. Controlled source/output timing tests still need the listening window and confirmed intended speakers; preserve existing queues/groups. |

### Priority 1B acceptance

No W acceptance item is WORKING until deployed and exercised in the real house.

| Test | State | Evidence / next requirement |
| --- | --- | --- |
| W1 cross-device | IN PROGRESS | Synthetic web checks at 1440x900, 1280x800 and 390x844; actual phone/AirTouch/PC still pending. |
| W2 profiles | IN PROGRESS | Same service profiles/admission; synthetic exact native-user and exclusive ABS source propagation, with missing/empty/shared map failures. Selected label is not authentication; live isolation still pending. |
| W3 unified search | IN PROGRESS | Web calls the existing broad MA search/collections service; child browse restrictions retained. Actual representative catalogue tests pending. |
| W4 playback | BLOCKED | MA protection repair and audible window pending. |
| W5 queue editing | IN PROGRESS | Prepared capability-gated non-Spotify Add/Play Next and owner move/remove, protected committed prefix, reduced queue view and explicit checked takeover. Concurrent/stale requests, uncertain outcomes, paused/buffering ownership and progress/timer isolation tested locally. Spotify queue additions, clear/undo, broader-source edits and full large-queue paging remain incomplete. No live acceptance. |
| W6 transfer | BACKLOG | Native compatible-player transfer and lease/progress handoff require implementation and acceptance. |
| W7 multi-room overview | IN PROGRESS | Admitted speaker state, checked session owners, join/leave and owned controls prepared; actual independent sessions untested. Joining never takes over another profile's queue/progress. |
| W8 sleep timer | BLOCKED | Existing timer backend reused; live timed stop awaits test window. |
| W9 child playback | BLOCKED | No child Spotify account; shared allocator repair/test pending. |
| W10 parent control | BLOCKED | Existing shared-screen person context; actual child-session inspection/stop untested. |
| W11 podcast resume | BLOCKED | Native source available; new end-to-end episode/progress test pending. |
| W12 audiobook resume | BLOCKED | ABS install/accounts/exclusive native assignments pending. Prepared routing passes two-person same-book tests locally; must verify distinct native/local positions and bidirectional sync on real backends/devices. |
| W13 radio | BLOCKED | Triple M native builtin identity retained; audible web playback pending. |
| W14 ambient timer | BLOCKED | Free sources visible; actual source/account/timer verification pending. |
| W15 Spotify contention | BLOCKED | Restore pinned guard. Re-read four intended mappings/six users, exact filters and leases; verify empty/missing/reconnected maps never expand access or select Renae. |
| W16 context ranking | IN PROGRESS | Local planner uses known HA hour/weekday and actual metadata, with neutral unknown context. Explicit seed/request precedence tested. No inferred school/calendar/presence, native usage learning or live presets. |
| W17 radio from track | BACKLOG | Scoped native seed/continuation with repeat avoidance and feedback. |
| W18 genre/era station | IN PROGRESS | Saved recipe/query preferences and proposal ranking implemented/tested locally. Actual evolving playback and protected Spotify catalogue bridge remain incomplete. |
| W19 steering | IN PROGRESS | More/Less/Never and reset persist at explicit preview-session/station/profile scopes; scope isolation tested. Applies to previews only until reviewed playback/continuation integration. |
| W20 saved recipe | IN PROGRESS | Restarted recipe regenerates fresh eligible proposals with repeat/exclusion persistence in synthetic tests. No static playlist saved. Real native queues/household acceptance pending. |
| W21 Keep It Going | BLOCKED | Explicit control now gates owned pinned session, healthy guard and selected-source similar-track capability. Actual repaired backend/end-of-queue tests pending; new recipe feedback is not wired into continuation. |
| W22 presets/groups | BACKLOG | Membership metadata is not sync/volume proof; preserve groups until tested. |
| W23 browser playback | BACKLOG | Capability-dependent native MA browser endpoint, with normal auth and explicit user start. |
| W24 recovery | BLOCKED | Approved restart required. Recheck source-filter pruning/empty-map default-full-access risk, pin integrity, UI auth expiry and all saved state; no source deletion requested. |

### Player inventory (read-only snapshot)

“Available” means native MA availability, not audible operation. Cast-origin
activity is independent of MA queue ownership; no takeover was attempted.

| Household destination | Preserved HA entity | Live observation |
| --- | --- | --- |
| Kitchen Hub | `media_player.the_kitchen` | Available; reports external Spotify activity. Google Nest Hub, not Chromecast Audio. |
| Living Area Speakers | `media_player.kitchen_wall_audio` | Available, idle; existing Pi analogue path, volume 10%. |
| Kitchen Speaker | `media_player.kitchen_speaker_2` | Unavailable; Chromecast Audio. |
| Maddie's room | `media_player.maddie` | Available; reports Spotify activity. |
| Edie's room | `media_player.edie_s_speaker_2` | Available; reports Spotify activity. |
| Flynn's room | `media_player.flynn_s_speaker_2` | Unavailable; Google Home Mini. |
| Master bedroom | `media_player.master_bedroom_speaker` | Available; reports native relaxing-sounds activity. |
| Workshop | `media_player.workshop_speaker_2` | Available, idle. |
| Spare | `media_player.spare` | Available, idle. |
| Upstairs Lounge TV | `media_player.downstairs_tv_2` | MA available, idle; device registry identifies Samsung UA75RU7100WXXY. Polk output not physically verified. |
| Downstairs Speaker | `media_player.downstairs_speaker` | Unavailable; registry identifies another Chromecast Audio. |
| Lounge Room TV | `media_player.lounge_room_tv` | Unavailable; registry identifies Chromecast. No confirmed Hisense mapping found. |
| CarPlay | `media_player.carplay` | Native MA available, idle; no physical household-output acceptance. |

Fresh native capability read: Cast single speakers advertise pause, seek,
next/previous, volume and mute. Living Area Pi/TV/CarPlay expose volume/mute and
membership capabilities but do not declare the same transport set. New web controls
use an allowlisted projection; grouping/sync remains unverified regardless of flags.

## BACKLOG

- Retain honest unavailable/coming-later Call state; no new intercom work.
- Full ambient category coverage, household loudness calibration and confirmed
  group playback after the core acceptance path works.
- Other media endpoints (including CarPlay) only after the requested rooms.
- Productisation outside the newly requested media app, wall redesign, Due Work,
  AI work and other unrelated features. Guest/QR access is not an auth bypass.

## Local verification and deployment boundary

Latest full run: 945 Python and 80 JavaScript regressions passed. Four further
radio compatibility rejection cases were added and the 21-case radio file passed
afterwards. Ruff and privacy checks pass (352 source files scanned).
Synthetic Media phone/tablet/desktop checks cover join/add/Play Next, move/remove,
explicit takeover review/confirmation, escaped queue titles, stale conflicts and
refresh without replaying the command. Backend tests cover current/buffered item
protection, concurrent confirmations, uncertain results, native queue progression
without title deduplication, and per-person progress/per-room timer isolation.
Station tests cover recipe restart, proposal repeat gaps, scoped feedback/reset,
explicit-request precedence, unavailable/restricted sources, and slow catalogue
searches that preserve concurrent controls and newer recipe/progress state. The
responsive browser harness also checks recipe forms, preview-only actions, scoped
feedback, escaping and unavailable-source controls. Isolated connection
browser checks pass; these use no real household playback. The existing reviewed MA restore bundle remains the
original clean-HEAD source/hash, independent of newer undeployed Home Starter
book-routing/UI source. No adapter execution, Node-RED flow, Core/MA restart,
Audiobookshelf install/start, source-filter write or new access was performed.
No further Pi microphone capture was needed or performed for this queue slice.

## Verification and change boundary

- Earlier media web/source baseline: 827 Python and 77 JavaScript tests passed.
  The latest counts and targeted additions are recorded above.
- `devtools/e2e_media_app.py` passed with fictional loopback data at phone/tablet/PC
  sizes, including no automatic playback, child browse restriction, escaped labels
  and initial/mid-session authorization failure. Ignored synthetic previews exist
  locally; they are not screenshots or acceptance of the private real house.
- Isolated `devtools/e2e_connections.py` passed with synthetic fixtures and no
  Google account access. Initial sandbox scratch-directory failures were resolved
  by running checks with normal local temporary-directory access.
- Earlier local Home Starter tasks were inactive; their final handovers were read.
  Repository began clean at `2b7cba8`. No competing task was messaged or started.
- Live reads used existing matching HA credentials and ordinary ephemeral ingress.
  No tokens printed or saved; private audit scripts/bundle remain ignored locally.
- No approval denial occurred. Missing former SSH and unavailable browser routes
  are capability/access prerequisites, not denied operations. Current AirTouch
  mobile registration and historical network records were inspected; they contain
  no fresh DHCP/IP mapping. Protocol discovery, rather than a guessed address,
  identified the changed endpoint. Google accounts were not accessed.
- Node-RED /nodes and /flows were read successfully: Exec installed, revision
  present, one existing node and no Exec nodes. No flow deployed or executed.
- Three approvals requested upstream remain pending: MA repair/restart, backed-up
  AirTouch correction/Core maintenance, and localhost-only ABS installation.
  Audible tests, LAN exposure, accounts and credential grants remain separately
  gated. No additional requirement brief was treated as approval.
- No live playback, HVAC, dashboard, provider, permission, entity ID or kitchen-wall
  configuration was changed. Only non-secret repair staging files were copied to
  the existing HA share. No restart, commit, push or incomplete release made.
- No new family playback capability is claimed in this audit. Next: approve the
  existing MA console execution and arrange a listening window; apply the now-known
  AirTouch address repair in a safe Core window and resolve audiobook host/accounts.


## IN PROGRESS — catalogue and radio-display correction, 23 October

- Unified query aggregation is prepared for configured native MA sources that
  declare Search, with required matching native-user impersonation, explicit
  nonempty source filters, five-second per-source timeouts and isolated failures.
  Upstream identities are deduplicated; unrelated same-title items remain distinct.
  Instance-local IDs retain their namespace. Unsupported/offline sources and result
  limits are shown honestly. Spotify query/station execution remains blocked pending
  its reviewed allocator bridge; existing consented collection metadata is separate.
- Profile changes discard late searches. Revoked/empty/deleted mappings hide cached
  results/favourites/previews, reject stale selections and never grant unrestricted
  access. Person-bound screens cannot select another person's context. Scoped queue
  additions retain the owner's native user and require both users' source access;
  transferring such a queue's native identity remains unavailable.
- The supplied Nest photo is evidence of bad display metadata: Asset Stop plus time
  and date displaced Triple M's useful title. Fresh MA reads did not reproduce it:
  radio was idle with correct catalogue names and no current stream metadata. This
  does not establish whether the original cue came from LiSTNR, parsing or another
  upstream component. No stream was opened and no receiver command was sent.
- Local radio hygiene now rejects narrowly identified asset cue/time and bare ISO
  timestamp metadata, URLs and internal source markers. Web/AirTouch catalogue
  records and wall station labels use safe catalogue names. Genuine song/show names
  remain intact. A separate, explicitly uninstalled MA candidate filters radio
  updates before PlayerMedia/Cast and sanitises initial Cast radio metadata. It
  pins exact reviewed 2.10.7 source hashes and refuses mismatches before changes.
  This is NOT in the already-staged security repair bundle. It needs separate
  installed-source review, approval and real receiver tests, including fresh updates.

## BLOCKED — household replacement and cutover gate

The existing Google Home/Assistant routines and family entry points remain the
working household system. Local preparation and isolated approved repairs do not
constitute cutover permission. No defaults/routines were replaced, no duplicate
triggers enabled and no Google accounts accessed. Repository references describe
HA household routines, but no authoritative selected subset of Google routines
was established by the targeted local search. Grant must select the few routines
that should be replicated/improved; bulk migration is not proposed.

Full cutover requires a nearly complete cohesive core, actual cross-device family
use, useful Nest receiver metadata, verified queues/handoff/recovery and the
applicable M/A/W acceptance evidence. Resolve the selected routine subset and
agree a full cutover explicitly before changing default family access. Maintenance,
install or listening-window approvals alone do not authorise that cutover.
The minimum UX baseline remains the family's existing Nest/Spotify experience;
appearance or feature counts are insufficient. Broad W1-W24 remains incomplete.


Latest verification also passed the responsive Media harness at phone/tablet/PC
sizes, including profile changes during an aborted slow search and person-bound
profile limits, and the isolated connections harness. All browser data was
fictional loopback data. Full regressions use synthetic doubles where providers
or installed accounts are absent. The original staged MA repair archive hash
remains b9a5e655229137606e90f35c1bce00ee59def01b238172d39ca30737b6020a1d.
Two public official-source radio integrity hashes were manually reviewed and
recorded as nonsecrets; no token or private payload entered the baseline/source.


## IN PROGRESS — read-only comparison and common-flow usability

Fresh source/version audit confirms installed MA 2.10.7 started, protected and
stdin disabled. Three idle radio queues have correct station/queue labels and no
stream title; the AirTouch listening view has no stored session/current queue
label. Available MA logs: 100 lines, zero asset-cue/radio-metadata lines. This is
not reproduction of the photographed defect or proof of incoming stream content.
Exact installed audio/Cast/Player hashes cannot be read through the existing API;
the separate ignored RADIO_READONLY_HANDOFF.md provides a local-console hash-only
check, without installing/executing a candidate, creating access or restarting.
The candidate now refuses a changed Player mapper as well as changed audio/Cast
source. Its updated source is separate from the immutable staged repair archive.

Local responsive improvements: search before the player, results before browse
shelves, compact result cards, clear optional delayed start, specific busy feedback,
keyboard focus restoration and less implementation copy. Source failures and
unsupported operations remain honest. Synthetic screenshots at 390, 820 and 1440
pixels were reviewed. The browser harness checks touch heights, keyboard search,
focus, delay state, slow search/profile switching and existing ownership flows.
Latest targeted Python checks: 46 passed (including 22 radio cases); JavaScript:
80 passed; responsive harness, Ruff and privacy checks passed. Earlier full Python
run of 945 passed before these bounded changes. No deployment or household cutover.

## BLOCKED — exact radio compatibility and real acceptance

Required action: from the existing HAOS local root console, identify the current
MA container and return only the three installed public source hashes using the
separate read-only handoff. This is an operator/access prerequisite, not a denied
operation or an uncertain executed action. No remote execution/install was tried.
A match would establish source comparison only; a mismatch requires review. Fresh
receiver metadata and real-house playback still await the existing test/maintenance
approvals. MA repair/restart, AirTouch/Core maintenance, ABS installation, account
setup/exposure, controlled listening and full cutover remain separately gated.
Google routines/defaults and the family working system are preserved.


## IN PROGRESS — AirTouch card isolation after executor recovery

The executor disconnected before the camera-edit command could start. On recovery,
inspection confirmed the earlier panel-music timeout/validation changes were saved
and the camera patch was absent. Camera changes were then applied locally; no
uncertain live write or denied operation occurred. The newly supplied AGENTS.md is
current. No unrelated owner change was undone and no competing writer was started.

Concrete local fixes: Media's 12-second read deadline now includes ingress setup
and response parsing, rather than only fetch. Malformed/wrong-person/epoch data
fails into a retryable unavailable state instead of throwing across the card.
Playback retains its longer bounded response wait; uncertain POST outcomes are
not automatically replayed. Delayed-start selection triggers a visible refresh.
Camera images load lazily/asynchronously with reserved dimensions and an 8-second
card-only deadline, explicit unavailable state and Retry camera. Captured image
load/error events and per-image revisions reject stale callbacks; a lost camera
projection clears its image state. These changes do not share pending state with
navigation/climate or redesign the overview/person shell. Uncommissioned Call
continues to show setup status with no calling controls.

Fresh post-edit full validation: 950 Python tests and 85 JavaScript tests passed.
The JS suite includes injected stalled ingress, malformed/null rows/wrong profile,
slow/error camera, retry, stale events, projection loss and uncertain playback
response tests. Mock climate controls and navigation remain usable; no real HVAC,
camera or playback is operated by these tests. Ruff lint/format, privacy and diff
checks pass. Responsive Media and isolated connections browser harnesses both
passed with fictional loopback data. Native button-card/Lit and real-device camera acceptance remain
unverified, and no family capability is newly labelled WORKING.

## BACKLOG — overview geometry comparison before visual acceptance

Source-only observation: panel-layout.css currently defines a three-column grid
with Climate spanning the left top two rows, Today upper-right, Call/Cameras in
middle-right and Media/Home below. That differs from the owner handover's smaller
middle Home/Media and wide lower Cameras/Call. The source geometry was left
unchanged as requested; it is not evidence of what is deployed. Reconcile the
actual AirTouch view with the approved reference before changing any placement.
No new household behaviour choice is required for the isolation fixes.


## IN PROGRESS — deployed layout reconciliation and readiness matrix

Authorised HA dashboard read confirms 85 AirTouch views and House present. The
complete current panel-layout.css is embedded unchanged in saved deployment.
The landscape areas are Climate/Today across the top, Climate/Call/Cameras next,
then Media/Home; the smaller-container stacking rule is also deployed. This is a
deployed configuration discrepancy with the owner handover, not merely local
source drift. Actual Android viewport, loaded dashboard and physical rendering
remain unverified. The archived Oct17 config and Oct15/16 commits use the same
placement. Earlier documentation calls that composition approved, but the newer
handover describes different lower/middle positions. No geometry was changed and
no wall reference was repurposed as an AirTouch reference. HOUSE_ACCEPTANCE.md
records the exact comparison, all 42 acceptance tests, prerequisites and shortest
safe completion path. No new runtime capability, approval or cutover was inferred.

The latest handover remains the positional target; historical approval wording
does not override it. No new household layout preference is requested by this
read-only comparison. Actual Android view/viewport and reference fidelity remain
to be checked before a bounded correction.


## IN PROGRESS — bounded W6 and current-card rationalisation

The native transfer research found that upstream 2.10.7 moves queue/position but
not queue userid or Home Starter account leases. The shared service therefore
requires a reviewed native-owner bridge rather than blindly using the raw native
command. Prepared a separate opt-in ma_transfer.py candidate with exact official
source byte pins, native locks, source/destination/user-permission revisions,
native transfer reuse and userid/context preservation. It is not installed or
registered and is separate from the immutable security repair archive.

The service and both UIs now implement Review -> Confirm -> Check move, with an
empty destination, same owner/profile/session, native queue/user/position proof,
absolute timer preservation and explicit quiet paused staging. A persisted intent
precedes the single command. Partial/lost/cancelled replies are reconciled by reads;
no automatic resubmission or rollback touches other listening. Affected rooms and
their timers wait while uncertain, so a stop deadline can be late until ownership
is verified. Ordinary other-profile starts cannot replace the moved session.
Spotify, scoped catalogue, book/podcast and group moves are unavailable, retaining
their existing account lease and progress. Native clients do not share a universal
compare-and-swap transaction; no cross-client atomicity claim is made.

Card/page audit under the latest owner direction:

| Card | Concrete local improvement / retained path | Remaining live prerequisite |
| --- | --- | --- |
| Climate | Unknown zones say unavailable/reporting, not 0 enabled. Native thermostat and six-zone destination retained. | Approved connection/Core repair and household-safe operation. |
| Today | Same fresh owned House briefing as its page; expired legacy calendar items hidden. No private/stale fallback when projection exists. | Current selected data and real glance/family test. |
| Home | Unknown lighting no longer implies all off. Selected room controls and return navigation retained. | Actual selected-control usability. |
| Media | Shared owned-session title beats stale HA cue; technical cue fallback, finite move review and uncertainty states. | Native source review/deployment, listening window; unsupported source moves remain disabled. |
| Cameras | Summary reports selected/reporting metadata only from fresh binding; page retains 8-second isolation, unavailable/retry. | Actual supported images and native event/device testing. |
| Call | Not commissioned/unavailable stays honest; no callable controls without fresh commissioned proof. | Deliberately deferred; not a blocker to other cards. |

## IN PROGRESS — corrected uninstalled source-pin preparation

Found Windows newline translation in the downloaded review copies. Re-fetched
exact official response bytes using write_bytes and corrected only the uninstalled
radio/transfer candidate pins and read-only radio handoff expected values. The
original staged repair bundle remains unchanged. Earlier expected radio hashes
were CRLF-copy hashes and are superseded; nothing was installed or executed with
them. A regression now rejects newline-rewritten source. Eight public source
integrity hashes were manually reviewed for the privacy baseline, not credentials.
The read-only hash command is unchanged. Installed compatibility is still unproven.


## IN PROGRESS — final bounded checkpoint

After the completed transfer candidate and AirTouch summary changes: full Python
986 passed, JavaScript 91 passed, both isolated browser harnesses passed, Ruff
lint/format and privacy passed (357 source files). The native candidate has no
further active implementation in this slice. Its exact external gate is installed
MA source/function compatibility review, separate approval to register/deploy its
existing-admin-scope commands, then a controlled real playback window. It remains
uninstalled. Radio has its own corrected exact-byte pins and approval gate. The
staged security restoration archive remains byte-identical at its recorded hash.
All cards/destinations were audited; current layout/styles/IDs remain intact.
No live device acceptance, deployment, account setup or cutover is claimed.
Next bounded local page work: finish ordinary AirTouch Media controls and source/
search presentation using the shared service, without expanding bridge scope.


## IN PROGRESS — ordinary AirTouch Media controls and shallow browsing

Audited current controls before editing. Added the missing owned-session Stop
through the shared Listening API, with no HA fallback for backend-controlled
playback. Pending reads/actions disable those controls; repeated Stop taps produce
one POST. Other profiles' sessions do not gain Stop. Search/browse/results now
precede library shelves, with explicit Back to choices and Clear search; folder
and back operations remain metadata-only. Item types are labelled Song/Album/
Playlist rather than generic Music. Empty/unavailable results keep other shelves
usable. Request generations and route identity discard late older responses and
responses after leaving Media. Household Back/House navigation remains unchanged.

Final aggregate: 986 Python and 94 JavaScript tests passed; Ruff lint/format,
privacy (357 files) and diff checks passed. Both isolated browser harnesses passed.
A further network-blocked AirTouch Media template check at 390/820/1440 verifies
fit, Stop/Back/Clear, empty/source-unavailable text and 44px touch heights. This
CSS/HTML fixture is not native HA/Lit or physical-console acceptance. All native
candidates remain uninstalled, geometry/IDs preserved and live holds unchanged.
The radio operator handoff now explicitly marks older CRLF-copy expected hashes
superseded and retains only corrected exact-byte expected values.

## AirTouch destination audit — 23 October, local only

IN PROGRESS: existing layout retained. Today now distinguishes fresh empty,
partial and unavailable selected sources; overview and focused pages agree.
Home/room controls omit unknown numeric sliders and stale climate readings; moving
blinds are labelled moving. Person speaker status follows shared-service availability.
Unavailable camera Talk cannot execute; malformed Call destinations stay contained.
Duplicate in-flight provider taps issue one command, with pending cleared on result.

Validation: 986 Python and 102 JavaScript tests, Ruff lint/format, privacy scan,
loopback media/connections browser harnesses and synthetic AirTouch Media fit at
390/820/1440 pass. The first privacy attempt hit a sandbox temporary-file permission
error; the authorised local retry passed. No live action or uncertain command outcome.
Native HA/Lit rendering, physical camera images, HVAC operation, audio and family
acceptance remain unrun; deployment/maintenance/install/control/cutover holds persist.
Next: approved isolated deployment and existing commissioning prerequisites in the
acceptance matrix, rather than more speculative features.

## Isolated preview preparation — local only

IN PROGRESS: separate `panel_preview.prepare/verify` configuration transform and
preview-only execution facade prepared. Production renderers are unchanged by this
slice. Existing state/projection reads and internal preview navigation remain;
service/WebSocket/fetch calls, original action callbacks, forms and native controls
are blocked. Native camera/control consumers become read-only summaries; images
are suppressed. The preview is visibly labelled and never becomes a default.

989 Python / 102 JavaScript aggregate passes; separate Chromium guard test covered
59 generated fields, 331 event-handler checks, repeated events and keyboard
navigation with zero escaped calls or browser requests. Source input remains
unchanged and tampered preparations are rejected. This is not an arbitrary-code
security sandbox and does not alter HA user rights.

BLOCKED: preview publication requires the specific pending approval. No live
dashboard, service, permission or other household change was made. Generation,
review, separate publication and rollback steps: [AIRTOUCH_PREVIEW.md](AIRTOUCH_PREVIEW.md).
All maintenance/install/control/cutover holds remain unchanged.

## WORKING — authenticated media web interface deployed

HA Green's existing `6726420e_home_starter` add-on is started at 0.8.40. Real
`/media` rendering, profile heading, search and Now playing were verified through
existing authenticated ingress with zero browser errors and no control requests.
Unauthenticated access returns 401. Served JS/CSS/manifest match release Git blobs.
This is working interface/read access, not audible playback or family usability.

All four managed dashboard configurations and the registry match their pre-update readbacks; saved
household configuration is unchanged. The initial guard stopped before any update
because four runtime `/items/*/state` values changed. A tested comparison excludes
only those live states and still guards every configuration/identity/ownership
field. No default-dashboard, Google routine, credentials or network writes occurred.

CI passed for release commits 25ad0c4 and d868b7b, including 989 Python/102 JS tests,
app lint and amd64/arm64 builds. Scoped rollback backup `5edf25a5` contains 0.8.39;
its private 68,198,400-byte downloaded archive SHA256 is
`f026ee07208c7865196c58376dbd226028b04664c78b1486d3b27a05cd667771`.
The backup held six listener profiles and no active timers, leases or handoffs;
no Supervisor jobs were active before the update. The completed update job was
`2f7c303e43024e7b873487e505db819d`. Restore only Home Starter from that backup if
rollback is needed; preserve the current defaults/dashboards and inspect new work
before replacing app data. No rollback was required or executed.

## WORKING — corrected native web entry

Use `http://192.168.68.119:8123/app/6726420e_home_starter`, then **Open Household
Audio**. The earlier delivered `/hassio/ingress/...` link was obsolete and returns
404 on HA 2026.10.2. Native `get_panels` registers `app`, not `hassio`. The existing
version-aware navigation helper already selects `/app/`; the incorrect link was
in the delivery report, not the deployed button. Its relative `media` href and
server-injected base preserve the authenticated ingress prefix.

Actual native HA browser entry and button click-through now pass: outer HTTP200,
media profile/search visible, zero page errors or mutation requests. Authentication
was held only in an ephemeral browser context and discarded. Existing 25 navigation
tests pass. No further production update/restart or settings change was required.

## IN PROGRESS — reported web refresh greying repair

Reproduced in the real authenticated interface: the seven-second poll set global
busy, disabling All collections at 7.19s, 14.21s and 21.19s for roughly 0.6–1.3s.
The 0.8.41 repair separates silent background reads from foreground/action locking,
bounds GETs, preserves last confirmed state on refresh failure, discards old reads
and protects in-flight mutations/repeated taps. Server ownership/source enforcement
is unchanged and still checked against fresh native state. Local browser race,
timeout/failure, profile/room, source rejection and auth-loss tests pass; production
verification follows the approved scoped add-on update. No playback is tested.
