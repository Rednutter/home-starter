# Household Context — 0.6.0

## Baseline and scope

Started from actual `main` at `07fe46a0dd14433920b20483fb33cbaf3cbff833`
(0.5.4), already ahead of the brief's expected 0.5.3. The household Green was
running 0.5.3 at implementation start and subsequently updated to 0.6.0. This release adds a deterministic context projection and its
first consumer, a passive native HA wall. It does not redesign the AirTouch/shared
tablet, install calendar providers, infer occupancy or change physical display power.

Reused: This House confirmed native people; Home Readiness source selection,
identity-bound event verification and display admission; existing screen preferences,
preview/publication fingerprints, registry reads and private storage. Music,
room/device ownership and existing dashboard controls remain separate.

## Model and persistence

`context.py` owns parsing, proximity, explicit departures, rules and bounded Markdown.
`context_runtime.py` reads selected native sources and projects them per admitted wall.
`static/context.js` edits only explicit preferences through admin-only `/api/context`.
The calendar remains authoritative for events and HA Person remains authoritative
for people. There is no copied registry, calendar database or inferred relationship.

Private Home Readiness storage advances from version 1 to 2, adding:

```text
context.rules[] = {id, text, people:[HA Person ID], start, end, weekdays:[0..6]}
context.events[event hash] = {people, travel_minutes, buffer_minutes,
                             round_minutes:5|10, routine_time}
```

Dates are inclusive for rules. Empty people means household-wide. Event hashes bind
the native source identity, title and exact start/end; edits to that occurrence or
source require a new explicit link. Recurring-event association is not inferred.
Rules are limited to 30 and event links to 100. Event titles/payloads are not saved
in Home Starter preferences. Existing links can be removed even while the source
is unavailable.

Version 1 loads with empty context in memory, preserving choices, verification,
members, devices, revision and household epoch. Reading does not rewrite the file;
the next explicit save writes version 2. Unsupported/corrupt versions fail safely.
Saves check current revision/epoch, validate confirmed people and invalidate old
previews. Other Readiness saves retain context.

## Temporal behaviour

- One chosen consolidated HA calendar, plus the separately chosen dated collection
  source where wanted. Native provider setup and Readiness verification are reused.
- Fetch the current local day through the next 21 days. Parse aware timed events
  and exclusive-end all-day events; reject malformed envelopes and invalid ranges.
- Order chronologically using actual instants, including DST folds. Scheduled-end
  elapsed events leave the display without being declared completed.
- Current/approaching commitments gain emphasis. Busy mornings with three or more
  remaining events show only two farther rows; quieter periods admit more upcoming
  information, bounded to 14 minus today's count, with at least four farther rows.
  Today's list is capped at eight with an explicit remainder count.
- Phase is local clock-based: morning 05–10, daytime 10–15, afternoon 15–20,
  night otherwise. It does not claim that anybody is home or away.
- Leave-by uses explicitly entered travel and margin or an explicit earlier routine,
  rounded earlier to a five- or ten-minute boundary. Missing travel evidence produces
  no calculated estimate. A routine later than the commitment produces no departure.
- Morning rules require matching inclusive dates, weekdays and still-confirmed
  people. No rule, school ownership or activity association is inferred from names.
- Waste uses the existing verifier's dated collection/service recognition, never a
  default collection schedule. Weather uses the admitted native current condition;
  explicit severe conditions may gain emphasis. No forecast advice is invented.

## Publication, freshness and privacy

Preview is read-only. An explicit wall publication opts that saved surface and
household epoch into context updates. Other profiles and existing published walls
are not silently republished. The worker checks the current saved dashboard
fingerprint and owned context sensor before updating; external edits stop updates.
Reset requires a fresh explicit publication. Concurrent choice/reset changes
discard an older read before publication.

Each opted-in wall receives a deterministic `sensor.home_starter_context_<hash>`
through HA's supported REST state API, with state/attribute readback. This is a
transient projection, not an entity-registry replacement. It contains the bounded
rendered near/ahead rows, timestamps, counts and ownership. The worker refreshes
every minute; native Markdown templates suppress data after its 150-second validity
deadline or 180-second maximum age. It recovers after app restart. Failed source
reads clear old calendar rows instead of reusing cached events. Identity changes,
expired proofs, hidden sources and screen exclusions block content.

The existing 24-hour Readiness proof lifetime remains: background reads do not
silently renew household verification. Explicit re-verification is required.
Personal screen profiles without a verified native Person mapping suppress
person-specific rules and event links rather than matching names.

Publication warns that rendered calendar/rule text enters HA state and may enter
its recorder/history. HA account permissions apply; this is not a kiosk security
boundary. Home Starter stores only explicit preferences/hashes, but HA owns the
projection's visibility and retention. Calendar text is escaped before Markdown
rendering. Credentials, household event contents and live screenshots stay private.

## Wall and administration

Native Sections/Markdown provide two compact columns: Today and Coming up. Small
time/date/current-condition context leads the display. Quiet time expands its
horizon; the same layout gives busy commitments more emphasis. No generated
controls, permanent people cards, large clock or decorative fill. Native HA chrome
remains; hiding it and physical sleep/wake require a separately verified display path.

Household Context is one optional administration disclosure: source handoff,
current context, morning rules and explicit event/departure links. Save/discard/
refresh preserve drafts and returning state. The commissioning handoff now reopens
Home Readiness correctly within the existing collapsed Review setup section.

## Acceptance evidence

- **411 Python tests**, including 64 context tests; **18 JavaScript tests** passed.
  Ruff lint/format and whitespace validation passed.
- Browser flows passed: installation, returning setup, inventory, Home Readiness,
  six commissioning cases, touch, This House and Music with both normal and limited
  progress evidence. Context rule/departure save, reload and preview passed on
  desktop 1280×900/light and mobile 390×844/dark.
- Native publication/control regressions passed on disposable HA 2026.10.0:
  phone/tablet/specialist/wall, native light control and climate target change with
  restoration, and phone/mobile template values. Fixtures support a bounded
  loopback port offset because Docker's Windows port reservation covers old ports.
  Native numeric assertions accept HA's whitespace formatting while retaining
  the exact expected values.
- All eight fictional wall scenes rendered and were visually reviewed on actual
  disposable HA: busy morning, quiet morning, daytime, afternoon, evening after
  scheduled activities, weekend, no calendar and temporarily unavailable calendar.
  Captures are ignored local artifacts in `screens/context-native/`, including
  1280×720 busy/quiet variants and 1920×1080 originals. No actual household calendar
  data is in these fixtures. Native weather is not supplied in those eight scenes.
- `devtools/accept_context_native.py` passed the actual local vertical slice:
  native calendar event verification → preview → explicit dashboard publication →
  sensor readback → native template render → forced stale fallback → application
  restart → fresh context. Existing household settings remained unchanged and
  event text was absent from Home Starter persistence.
- Scoped Impeccable finish review covered all eight scenes, then rechecked the
  editor after one form-spacing fix. It returned ship. This is visual review,
  not proof of real household commissioning.

Architecture builds, app lint and tracked-file privacy validation are release
gates in CI. Consult the exact pushed commit's CI result for their outcome.

## Actual Green and remaining acceptance

Read-only Green inspection confirmed installed **0.5.3**, retained This House
confirmations, exact saved screen choices, three published dashboard statuses and
the original private Music connection/playback proof. No house registry, hardware,
dashboard or playback mutation was needed for this release's inspection.

The owner subsequently made the repository public and anonymous Git access passed.
The established Supervisor update path then installed 0.6.0 with rollback backup
enabled. Management and application readback both confirmed 0.6.0. Exact saved
screen settings, house review revision/people, Music connection/original proof and
all three published-dashboard readbacks survived the update. No credentials were
added. The new context endpoint returned empty preferences and honestly reported
that the household calendar is not selected.

Do not claim real calendar rendering, native wall operation, weather, physical
kiosk/power or household usefulness acceptance for 0.6.0 there.

The next bounded step is explicitly selecting/verifying the actual consolidated calendar and publishing one chosen
wall privately. Verify real temporal behaviour, reload and source failure before
moving to the separately selected AirTouch/shared-tablet consumer. Do not expand
into broad health/features while this acceptance remains outstanding.

## Public repository privacy review

The owner approved public access and a historical identifier scrub. The review
covered all published refs: 33 commits and 496 distinct file blobs before the
follow-up acceptance commit. No runtime exports or household screenshots were
tracked; the only binary files were the application icon and logo. Commit
identities were already neutral. Historical fixture/maintainer identifiers and
private-network example addresses were selected for replacement with neutral
identities and documentation-network addresses. Third-party public maintainer
contacts were distinguished from household data.

An old issue containing household names was privately archived and replaced with
sanitized issue #2 with the owner's explicit approval, because editing its current
body alone retained the old revision. Recovery material and detailed audit findings
remain in ignored local storage. The current ingress test identity is synthetic.
History rewriting removes identifiers from published branch history; it cannot
erase copies already downloaded or guarantee removal of GitHub's cached old objects.
Only sanitized source/fixtures belong in future commits, never runtime credentials,
calendar content, household exports or live screenshots.

Native mechanisms: [HA Markdown card](https://www.home-assistant.io/dashboards/markdown/)
and [HA REST API](https://developers.home-assistant.io/docs/api/rest/).
