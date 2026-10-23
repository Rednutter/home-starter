# Household Audio web app

Priority 1B is part of the existing Home Starter service. The initial web interface
is implemented but not deployed or accepted on the real household devices.

Open `media` beneath the existing authenticated Home Starter ingress URL. It uses
the same `ListeningRuntime`, profiles, account allocator, permissions, progress,
timers and speaker mapping as the AirTouch Media card. No separate playback engine,
public port, authentication database or provider credential store is introduced.

## Current source slice

- Phone uses a compact listening/control layout; tablet and desktop use a wider
  catalogue and room sidebar. The original asymmetric AirTouch House stays intact.
- Profiles, category browsing/search, favourite/recent items, free ambient/radio
  choices, single-speaker selection, owned-session controls, delayed starts and
  sleep timers delegate to the existing listening API. Selecting a profile or
  speaker never automatically plays media.
- House audiobook choices route into a person's listening context. Missing,
  unavailable and unverified libraries have explicit states. A configured source
  is not called verified. No account, provider or title is invented.
- MA player features are projected through a small allowlist. Pause, previous/next
  and volume appear only when declared. Supported queue additions use the native
  play-media capability. Play Next and owner move/remove controls require a verified
  queue/buffer snapshot. Group control and transfer remain pending.
- Surprise Me is absent when the account guard is unavailable. Renae's pending
  personal provider does not fall back to shared discovery. Browsing remains usable.

`GET /api/listening` returns only screens that pass existing display authorization.
`GET/POST /api/listening/{surface}` remains the common data/control interface.
The web client exposes only that admitted surface's normal profile choices.
The generic HTML shell contains no household data. API access still requires the
authenticated HA ingress identity and configured control-screen binding. Profile
selection changes context; it is not authentication as the named person.

The optional remembered profile stores only an opaque profile ID, after a deliberate
checkbox choice. Every request is authorized again. A 401/403 clears household
content. No service worker or offline private-response cache is registered.
The generic PWA manifest is prepared; installation depends on browser/secure-context
support and remains unverified. No QR bearer grants or anonymous guest access exist.

## Audiobook isolation boundary

Native MA supports one ABS provider per backend user, assigned exclusively through
that MA user's source filter. The prepared routing now checks one explicitly bound
person/source, the matching enabled native user, a nonempty exclusive source filter,
and the reviewed MA 2.10.7 native impersonation API. It passes that user's required
builtin identity to `player_queues/play_media` and the exact provider-instance URI.
Native ABS resume is authoritative; local history cannot seek over it. Existing
listener-local progress remains for sources without native progress routing.

Missing/deleted/shared providers, empty filters (including other unrestricted
users), duplicate users and unsupported versions fail before queue mutation.
Assignments are rechecked before saving progress or operating owned sessions.
Spotify collection reconciliation preserves existing explicit progress-source
assignments and never adds these providers to everyone. No native filter is
changed by selecting a profile or playing a book.

These are local implementation and synthetic-test results, not commissioned ABS
isolation. The synthetic same-title test resumes two native identities at 123 and
907 seconds, preserves both local histories, rejects an emptied filter, and sends
no compensating seek. Real two-person native progress, bidirectional sync and
recovery tests remain required. Existing native API permissions must suffice;
permission failure must not trigger a new token, broader grant or owner fallback.
A profile label or account login is insufficient.

References: [MA multi-user progress](https://www.music-assistant.io/settings/user-management/#audiobook-and-podcast-progress-sync-in-a-multi-user-environment)
and [ABS provider setup](https://www.music-assistant.io/music-providers/audiobookshelf/#multi-user-environment).

Do not let native source removal empty a user's filter and expose the whole library.
After repair/reconnect, re-read all six users, the three connected Spotify mappings,
Renae's pending personal-only binding, explicit source assignments and active pinned
enforcement. No source deletion or access expansion is part of this slice.

## Queue participation and conflict handling (prepared locally)

The dedicated app and AirTouch Media use the same service model. A permitted room
shows a checked queue owner and reduced queue titles. Join listening records
participation in that exact household session; it copies no progress and grants
no replacement, stop or timer ownership. Leave listening changes only participation.
Choosing another speaker never starts playback. Foreign playing, paused and
buffering sessions reject replacement, including after joining. A user may replace
their own checked queue; the new UI labels that operation "Replace my queue".
Supported non-Spotify music queues offer Review takeover, then a separate Confirm
takeover action. The confirmation expires after 30 seconds and is bound to the
same profile, exact queue revision and target player. It transfers household
control while retaining queue contents and playback state; it sends no playback
command. The old timer bound to that exact session is cleared, as disclosed during
review. Saved histories/progress and timers for other rooms remain separate.
Children cannot take over another profile's queue. Spotify and progress-source
takeover stay unavailable. Confirmation is UI intent state, not authentication or
an access grant. Queue ownership still depends on existing display authorization.

Queue additions require the owner or an explicit participant, a fresh queue revision,
MA 2.10.7, a permitted single player advertising play-media, and a supported finite
non-Spotify track source. Fresh metadata resolves an exact previously offered source
instance; combined-library URIs cannot choose a different account. The service
rechecks the revision after metadata lookup, sends native MA `option=add`, then
checks that the previous queue prefix/current item survived and exactly one item
was appended. It retains the original household owner and timer/progress scope.
No queue replacement, implicit playback start or automatic retry is used for Add.

Play Next uses native MA `option=next` after the already committed/buffered prefix.
The owner can move upcoming items one place up/down or remove them using native
MA commands. Joined participants can add or Play Next but cannot reorder/remove.
All edits require reviewed MA 2.10.7, known supported track sources for every queue
item, an unshuffled playing/paused queue, and verified current/buffer indexes.
Current, played and buffered entries stay protected. Missing fields, buffering,
unsupported sources/players and stale opaque row handles disable the operation
with an explanation. Each result is read back against the expected order and
unchanged current item. No automatic retry or rollback replaces anyone's queue.

Spotify additions remain unavailable: the reviewed adapter currently exposes a
replacement operation, and additions must not bypass its account pin/leases.
Audiobook/podcast progress sessions, radio/ambient queues, unsupported players,
unreviewed versions and queues too large to check fully in the current bounded
inspection also reject Add. These limitations are shown honestly. Source/player
permissions and child approved choices are checked in the service, independently
of hidden or disabled UI controls. Native queue-item IDs, raw payloads and delivery URLs do not
appear in the reduced queue view.

The runtime lock serializes this service's callers. Native MA/external clients are
not locked by it: a change during Add produces an uncertain-result message and a
read-only refresh, without retry or destructive rollback. This is not an atomic
cross-application takeover mechanism or completed W5 acceptance. Account-pinned
Spotify additions/Play Next, clear/undo, full large-queue paging and broader-source
editing still need further work. Takeover confirmation does not lock native clients;
subsequent controls must still recheck the owned session.

## Verification

### Station recipes and planning: preview only

The existing reviewed Spotify adapter uses provider catalogue search after the
sole allocator reserves an account, then pins similar-track continuation to it.
Its repeat exclusions are short-lived; it has no saved-recipe/persistent-feedback
protocol. Those reviewed adapter files and the staged archive were not changed.

The household service now saves per-profile recipes (name, text/artist/song seeds,
genres, decade preference, explicit policy, repeat gaps and discovery weighting).
It saves the recipe and run counter, not a static playlist. Each new preview
searches again and generates a fresh eligible proposal queue. Four short-lived
preview metadata caches support feedback; they are not playback queues.

Ranking is deterministic for the same inputs/run: seed and era affinity, recorded
artist familiarity, scoped feedback, verified metadata tags, then stable tie-breaking.
HA's configured timezone supplies hour/weekday when readable; otherwise context
adds no weight. Morning/night weighting is a soft suggestion, not an automation
or inferred school/bedtime routine. Explicit track requests/seed preferences win
over default context; hard content restrictions and Never exclusions remain.
Normal explicit search/play outside the preview planner is unchanged.

Track repeat windows and artist gaps use upstream identities, never titles.
Unknown artist metadata cannot prove a configured artist gap. Sparse results stay
partial/exhausted; provider errors do not trigger a personal-library, other-account
or relaxed-content fallback. More/Less/Never can apply to the current preview
session, station or profile's previews. Station/profile exclusions survive reload;
session tuning lasts only for its preview session. Reset explicitly clears only
the selected scope, retaining recipe/content restrictions. Editing a recipe expires
its old preview sessions. Real listening history is not fabricated: the service
currently records proposals separately; verified playback-history ingestion remains
to be connected. The pure planner also tests supplied playback-history constraints.
Preview searches run outside the shared listening lock. Commit rechecks authority,
connection identity and station-state revision, discarding stale results while
preserving concurrent controls, timers and audiobook progress updates.

Previews require reviewed MA 2.10.7 and an available non-Spotify source declaring
search plus track capability. They query each explicitly assigned capable provider with the matching required
native user, without a library fallback. Coverage reports configured sources,
failures and result limits; it remains unverified against real providers and never
claims the whole household catalogue. Spotify planning is hard blocked, even if a caller
supplies a supposed reservation flag: a reviewed bridge must run inside the actual
allocator/source enforcement before this can become Spotify station playback.
Renae is never an automatic fallback. Children cannot configure/preview unapproved
stations. Credentials and native provider/source permissions are unchanged.

The dedicated responsive web UI exposes create/edit, new/refined previews and
scoped feedback/reset with no Play/auto-start action. Existing Keep It Going is
now offered only for an owned pinned session whose current guarded source advertises
similar tracks; the backend checks again before enabling it. This does not connect
recipe feedback to the existing adapter or change its existing discovery behaviour.
Continuous/evolving station playback, rich item-based seeds, broad catalogue
coverage and feedback-enforced continuation still require implementation/review
and live acceptance. No preset, scheduled start or automatic playback was added.

Run Python/JavaScript regressions, Ruff and privacy checks, plus:

```text
python devtools/e2e_media_app.py
python devtools/e2e_connections.py
```

The Media browser harness uses synthetic loopback data only. It checks three screen
sizes, profile routing, escaped labels, no automatic playback, action delegation and
authenticated failure states. It is not live W1–W24 acceptance. Those remain on the
household completion board. No actual speaker/HVAC state is changed by these tests.

Next: complete the pending live repairs and appropriate approvals, deploy a coherent
core slice, use it on the real devices, then implement remaining native queue,
transfer/grouping, protected station playback/continuation and browser playback.
Illustrative tastes, volumes and bedtime times are not household preferences or
permission to apply presets. No upstream sync-back policy is changed.


## Profile-scoped catalogue query preparation

Queries aggregate explicitly assigned native sources, with per-source timeouts and
failure isolation. Native users must resolve uniquely and have nonempty known
filters. Spotify is excluded from this generic path. Search-capable non-Spotify
providers are supported by protocol/capability, not by claiming that Qobuz or any
other optional subscription is configured. Tests use fictional providers only.
Grouped results deduplicate upstream identities, never titles, and expose partial
coverage. Current per-source limit is 50, labelled incomplete when reached; this
is not a claim of exhaustive catalogue pagination. Existing paginated consented
Spotify collection metadata remains separate from broad catalogue discovery.
Search results, continuation pages and actions carry a private profile/source
receipt, rechecked after search and before transport. Revocation hides cached
results without deleting favourites or quietly expanding source access.

Station proposals remain separate from accepted playback and listening history.
The future Spotify bridge must reserve inside the actual pinned guard before any
provider discovery, bind searches/similar tracks to that reservation and native
user, enforce House -> House #2 -> Grant and never Renae overflow, and recheck
queue/session/source identity before execution. An uncertain command must be read
back before retry/release. Record history only from verified accepted playback.
This requires a separately reviewed adapter protocol/bundle, not changes to the
staged restoration archive. No bridge deployment or Spotify insertion is claimed.

## Radio metadata candidate and deployment boundary

`radio_metadata.py` supplies bounded display filtering. Catalogue station identity
is used for household radio labels; genuine song/show metadata is preserved by the
native candidate unless it matches narrow asset-cue/time or timestamp forms.
`ma_radio_metadata.py` is opt-in and uninstalled. It checks MA 2.10.7 plus exact
upstream audio/Cast/Player source hashes before wrapping the radio metadata update and
initial Cast payload builders. The reviewed Player model falls back to the queue's
catalogue station when stream title is empty; both initial receiver load and live
Cast updates use that metadata. Transport, artwork and queue identity stay intact.
No startup hook, repair archive, source credentials or playback path was changed.
Installed source compatibility, fresh receiver updates and audible/family tests
remain pending. No upstream cause is asserted from the supplied photo alone.

The existing Google family workflow remains in place. Keep this application in
isolated preparation until its cohesive core is nearly complete and family tested,
then obtain explicit agreement on the selected routine migration and full cutover.


## Read-only compatibility and usability audit, 23 October

Fresh Supervisor read: MA 2.10.7 started, protected true, stdin false. Reduced
native state showed three idle Triple M radio queues with correct catalogue and
queue labels and no current stream title/artist. The existing AirTouch panel's
listening view returned no stored session or current queue label. The available
100 MA log lines contained zero asset-cue or radio-metadata lines. These reads do
not establish the original cue's origin, incoming live ICY content, or current
receiver output. No radio stream was opened, receiver polled/controlled, service
restarted or source/candidate executed.

Exact installed source compatibility remains BLOCKED on three file hashes. The
existing authorised APIs do not expose MA source, stdin is disabled, and the old
SSH route/key is unavailable. No protection changes or execution flow were used.
A separate ignored `RADIO_READONLY_HANDOFF.md` beside the repair handoff gives
minimal local-console identification and source hashing only. It needs no copy,
installation or restart. The candidate checks all three reviewed files before
changing either hook; the security restoration archive remains unchanged.

The local common-flow audit found search below a tall idle player, results below
unrelated browse shelves, excessive implementation copy, lost keyboard focus and
an invisible delayed-start state change. Bounded fixes move search above the
workspace, put results first, compact single-item/nested result cards, retain
honest source limitations in an expandable summary, simplify idle/unsupported
copy and restore focus after requests. Delayed start is optional and explicitly
shows the selected delay; selecting it never schedules/starts audio. Search and
actions show specific pending messages, and the workspace exposes aria-busy.

The isolated browser harness passes at 390x844, 820x1180 and 1440x900, checking
no horizontal overflow, visible search, buttons at least 44 pixels high, keyboard
submit/focus, slow-search feedback, profile switching and protected queue flows.
Synthetic initial and search screenshots for all three widths were visually
reviewed under ignored `.runtime/media-app-preview/`. They contain fictional data
only. Phone first-result access still needs ordinary vertical scrolling; no live
latency, receiver handoff, audible success or Nest UX parity is claimed. Native
transfer/grouping, live protected Spotify discovery and audiobook progress remain
concrete acceptance gaps, not presentation problems solved by these changes.


## Shared AirTouch service failure isolation

The AirTouch Media page still uses the same authenticated Listening API and
person/house context as the responsive app. Local changes bound a GET's complete
ingress/read path at 12 seconds, validate response lists and profile/epoch, and
clear loading into a retryable honest failure. The 150-second mutation response
bound remains; uncertainty never automatically repeats a POST. Existing source,
allocator and session-ownership enforcement is unchanged.

The focused camera card now owns its own 8-second image deadline, lazy/async image,
loading/error state and explicit retry. Revision checks discard old image events;
projection loss clears the image. Camera timers never set the shared command
pending flag, and callbacks from a departed route do not change the new page.
Isolated JS tests cover slow/error/stale images, source loss, calling unavailable,
continued media/climate/navigation and uncertain playback outcomes. These are
synthetic template-contract tests, not native Lit/button-card or real AirTouch
acceptance. The existing asymmetric shell, footer/person navigation and climate
configuration were preserved. No service/account/security changes or deployment.


## Bounded deliberate playback transfer

The shared Listening service and web/AirTouch UI support prepare, fresh confirmation,
cancel-before-execution and read-only recheck. Confirmation names both rooms and
expires after 30 seconds. The destination must be available, single and empty,
with no app lease, saved queue, external playback or grouping. Source order,
current item, native user, state and permissions are checked again. The current
supported contract is finite non-personal tracks/radio/ambient only. Spotify,
profile-scoped catalogue, audiobooks/podcasts and groups remain unavailable; no
account lease or personal progress is remapped by inference.

A private durable handoff journal precedes one bridge command. Ownership/session
and exact timer deadline move only after source emptiness and destination queue,
user, position and state are confirmed. Paused moves use native auto_play=false
and remain quiet, with a verified staged lease for later explicit Play. Partial,
disconnected, cancelled or lost responses cause reconciliation, not replay or
rollback. The affected pair stays guarded while uncertain; its timer is retained
but cannot safely stop an unverified destination and may run late. Book progress
of both profiles and other room timers remain untouched.

ma_transfer.py is a separate opt-in uninstalled candidate, not part of the staged
restoration archive. It reuses MA transfer with native player locks, native user
context/permission checks, request receipts and exact reviewed source byte pins.
Only existing USERS_MANAGE scope may invoke its commands; it creates no access.
Its reduced snapshots contain hashes/IDs, not stream delivery payloads. Ordinary
native playback locks help but do not make every external edit transactional.
Installed source review, scoped deployment approval and actual playback tests
remain required. Profile progress/account transfer needs further native adapter
work and remains explicitly unavailable.

The current AirTouch layout/visual approach is now explicitly retained by owner
direction. Card summaries and destination functionality are the active target;
older positional handover notes do not authorise rearranging it.


AirTouch's ordinary controls now include owned Stop through this same service,
with duplicate-action guards and no native HA fallthrough. Its search/results
appear before library shelves; Back to choices and Clear search are metadata-only.
Late requests and departed-route responses cannot overwrite current choices.
Loading, empty/unavailable sources and ownership restrictions have isolated JS
coverage. Network-blocked CSS/HTML template checks at three widths supplement the
responsive web harness, but do not establish native button-card/Lit or real-device
acceptance. No unsupported transfer or source is enabled by these UI changes.
